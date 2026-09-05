import os
import sys
import shutil
import subprocess
import threading
import logging
import time
import re
from typing import Optional, Callable, Dict, Any, List

logger = logging.getLogger(__name__)

# Global tracker for active Cline CLI process
active_cline_process: Optional[subprocess.Popen] = None
active_cline_lock = threading.Lock()

# Live CLI Log Ring Buffer for web terminal streaming
cli_log_buffer: List[Dict[str, Any]] = []
MAX_BUFFER_LINES = 1000
buffer_lock = threading.Lock()

# Cached CLI version
_cached_cline_version: Optional[str] = None
_cached_version_lock = threading.Lock()

def add_log_entry(stream_type: str, text: str):
    """Appends a line to the live CLI log buffer."""
    with buffer_lock:
        entry = {
            "timestamp": time.strftime("%H:%M:%S"),
            "stream": stream_type,
            "text": text.rstrip("\r\n")
        }
        cli_log_buffer.append(entry)
        if len(cli_log_buffer) > MAX_BUFFER_LINES:
            cli_log_buffer.pop(0)

def get_cli_logs(since_index: int = 0) -> Dict[str, Any]:
    """Returns log entries since a given index for polling/streaming."""
    with buffer_lock:
        total = len(cli_log_buffer)
        if since_index < 0:
            since_index = 0
        slice_logs = cli_log_buffer[since_index:]
        is_running = False
        with active_cline_lock:
            if active_cline_process and active_cline_process.poll() is None:
                is_running = True
        return {
            "logs": slice_logs,
            "next_index": total,
            "is_running": is_running,
            "pid": active_cline_process.pid if (active_cline_process and is_running) else None
        }

def clear_cli_logs():
    """Clears the live terminal log buffer."""
    with buffer_lock:
        cli_log_buffer.clear()

def find_cline_executable() -> Optional[str]:
    """
    Locates the 'cline' CLI binary on the system.
    Searches system PATH and standard global node/npm locations.
    """
    found = shutil.which("cline")
    if found:
        return found

    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA", "")
        localappdata = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", "")
        
        candidates = [
            os.path.join(appdata, "npm", "cline.cmd"),
            os.path.join(appdata, "npm", "cline.exe"),
            os.path.join(appdata, "npm", "cline.ps1"),
            os.path.join(localappdata, "Programs", "cline", "bin", "cline.cmd"),
            os.path.join(localappdata, "Programs", "cline", "cline.exe"),
            os.path.join(program_files, "nodejs", "cline.cmd"),
        ]
        
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
                
        try:
            res = subprocess.run(["where", "cline"], capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            first_line = res.stdout.strip().splitlines()[0]
            if os.path.exists(first_line):
                return first_line
        except Exception:
            pass
    else:
        candidates = [
            "/usr/local/bin/cline",
            "/usr/bin/cline",
            os.path.expanduser("~/.npm-global/bin/cline"),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate

    return "cline"

def is_cline_available() -> bool:
    """Checks if cline CLI executable is installed and runnable."""
    exe = find_cline_executable()
    if not exe:
        return False
    if exe == "cline" and not shutil.which("cline"):
        return False
    return True

def get_cline_version(cline_bin: Optional[str] = None, force_refresh: bool = False) -> Optional[str]:
    """
    Detects the installed Cline CLI version string (e.g. '2.18.0' or '3.0.61').
    Results are cached in-memory unless force_refresh is True.
    """
    global _cached_cline_version
    with _cached_version_lock:
        if _cached_cline_version and not force_refresh:
            return _cached_cline_version

        bin_path = cline_bin or find_cline_executable() or "cline"
        is_windows = sys.platform.startswith("win")
        flags = subprocess.CREATE_NO_WINDOW if is_windows else 0
        try:
            use_shell = is_windows and (bin_path.lower().endswith(".cmd") or bin_path.lower().endswith(".bat") or bin_path == "cline")
            res = subprocess.run(
                [bin_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                shell=use_shell,
                creationflags=flags
            )
            raw = (res.stdout or res.stderr or "").strip()
            match = re.search(r"(\d+\.\d+\.\d+)", raw)
            if match:
                _cached_cline_version = match.group(1)
            else:
                _cached_cline_version = raw if raw else None
        except Exception as e:
            logger.debug(f"Could not determine Cline CLI version: {e}")
            _cached_cline_version = None

        return _cached_cline_version

def get_default_timeout_seconds() -> int:
    """Reads configured timeout minutes from config and returns timeout in seconds."""
    try:
        from modules.config_utils import read_config
        cfg = read_config()
        timeout_minutes = float(cfg.get("queue_timeout_minutes", 5))
        return max(10, int(timeout_minutes * 60))
    except Exception:
        return 300

def build_cline_command(
    prompt: str,
    cwd: Optional[str] = None,
    yolo: bool = True,
    timeout: Optional[int] = None,
    extra_flags: Optional[List[str]] = None,
    cline_bin: Optional[str] = None
) -> List[str]:
    """
    Constructs the CLI argument list for invoking Cline.
    Automatically adapts flags depending on whether Cline 2.x or 3.x is detected.
    """
    bin_path = cline_bin or find_cline_executable() or "cline"
    cmd = [bin_path]

    version = get_cline_version(bin_path)
    is_v3 = bool(version and version.startswith("3."))

    try:
        from modules.auth_utils import API_KEY
        api_key = API_KEY or "dummy"
    except ImportError:
        api_key = "dummy"

    # In Cline 3.x, -P (provider) and -k (api key) are supported flags.
    # In Cline 2.x, -P and -k do not exist and cause unknown option errors.
    # Cline 2.x reads OPENAI_BASE_URL and OPENAI_API_KEY from environment.
    if is_v3:
        cmd.extend(["-P", "openai", "-m", "gpt-3.5-turbo", "-k", api_key])
    else:
        cmd.extend(["-m", "gpt-3.5-turbo"])

    if yolo:
        cmd.append("--yolo")

    effective_timeout = timeout if (timeout is not None and timeout > 0) else get_default_timeout_seconds()
    if effective_timeout and effective_timeout > 0:
        cmd.extend(["--timeout", str(effective_timeout)])

    if cwd and os.path.isdir(cwd):
        cmd.extend(["--cwd", os.path.abspath(cwd)])

    if extra_flags:
        cmd.extend(extra_flags)

    if prompt:
        cmd.append(prompt)

    return cmd

def run_cline_cli_process(
    prompt: str,
    cwd: Optional[str] = None,
    yolo: bool = True,
    timeout: Optional[int] = None,
    visible_terminal: bool = False,
    extra_flags: Optional[List[str]] = None,
    on_stdout_line: Optional[Callable[[str], None]] = None,
    on_stderr_line: Optional[Callable[[str], None]] = None,
    on_complete: Optional[Callable[[int, str, str], None]] = None
) -> subprocess.Popen:
    """
    Executes the Cline CLI in a subprocess and streams output asynchronously.
    Supports timeout bounding in minutes/seconds, output buffering, and optional visible console windows.
    """
    global active_cline_process

    effective_timeout = timeout if (timeout is not None and timeout > 0) else get_default_timeout_seconds()

    cmd = build_cline_command(
        prompt=prompt,
        cwd=cwd,
        yolo=yolo,
        timeout=effective_timeout,
        extra_flags=extra_flags
    )
    cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    logger.info(f"Executing Cline CLI command (timeout: {effective_timeout}s): {cmd_str}")
    
    add_log_entry("system", f"--- Launching Cline CLI task ---")
    add_log_entry("system", f"Directory: {cwd or os.getcwd()}")
    add_log_entry("system", f"Timeout: {effective_timeout}s ({effective_timeout // 60}m)")
    add_log_entry("system", f"Command: {cmd_str}")

    stdout_accumulator: List[str] = []
    stderr_accumulator: List[str] = []

    # Inject OpenAI Base URL pointing to local Flask proxy
    env = os.environ.copy()
    env["OPENAI_BASE_URL"] = "http://127.0.0.1:3001"
    
    try:
        from modules.auth_utils import API_KEY
        env["OPENAI_API_KEY"] = API_KEY or "dummy"
    except ImportError:
        env["OPENAI_API_KEY"] = "dummy"

    # Avoid infinite AI SDK warning spam in logs
    env["AI_SDK_LOG_WARNINGS"] = "false"

    is_windows = sys.platform.startswith("win")
    bin_path = cmd[0] if cmd else "cline"
    use_shell = is_windows and (bin_path.lower().endswith(".cmd") or bin_path.lower().endswith(".bat") or bin_path == "cline")

    if visible_terminal and is_windows:
        flags = subprocess.CREATE_NEW_CONSOLE
        proc = subprocess.Popen(
            cmd,
            cwd=cwd if (cwd and os.path.isdir(cwd)) else None,
            creationflags=flags,
            shell=use_shell,
            env=env
        )
        with active_cline_lock:
            active_cline_process = proc

        def wait_visible_exit():
            global active_cline_process
            ret = proc.wait()
            add_log_entry("system", f"--- Cline CLI process finished with exit code {ret} ---")
            with active_cline_lock:
                if active_cline_process == proc:
                    active_cline_process = None
            if on_complete:
                try:
                    on_complete(ret, "Executed in visible terminal window.", "")
                except Exception as e:
                    logger.error(f"Error in on_complete callback: {e}")

        threading.Thread(target=wait_visible_exit, daemon=True).start()
        return proc

    # Standard Headless Streaming Execution
    flags = subprocess.CREATE_NO_WINDOW if is_windows else 0

    proc = subprocess.Popen(
        cmd,
        cwd=cwd if (cwd and os.path.isdir(cwd)) else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        shell=use_shell,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
        env=env
    )

    with active_cline_lock:
        active_cline_process = proc

    # Watchdog timer to ensure process terminates if timeout is specified
    if effective_timeout and effective_timeout > 0:
        def watchdog_timer():
            time.sleep(effective_timeout + 5)
            if proc.poll() is None:
                logger.warning(f"Cline CLI exceeded watchdog timeout ({effective_timeout}s). Terminating process.")
                add_log_entry("system", f"--- Cline CLI timed out after {effective_timeout}s. Terminating... ---")
                try:
                    proc.terminate()
                    time.sleep(1)
                    if proc.poll() is None:
                        proc.kill()
                except Exception as ex:
                    logger.error(f"Error terminating timed-out cline process: {ex}")

        threading.Thread(target=watchdog_timer, daemon=True).start()

    def stream_stdout():
        try:
            for line in iter(proc.stdout.readline, ""):
                stdout_accumulator.append(line)
                add_log_entry("stdout", line)
                if on_stdout_line:
                    try:
                        on_stdout_line(line)
                    except Exception as e:
                        logger.error(f"Error in on_stdout_line callback: {e}")
            proc.stdout.close()
        except Exception as e:
            logger.error(f"Error streaming stdout from cline CLI: {e}")

    def stream_stderr():
        try:
            for line in iter(proc.stderr.readline, ""):
                stderr_accumulator.append(line)
                add_log_entry("stderr", line)
                if on_stderr_line:
                    try:
                        on_stderr_line(line)
                    except Exception as e:
                        logger.error(f"Error in on_stderr_line callback: {e}")
            proc.stderr.close()
        except Exception as e:
            logger.error(f"Error streaming stderr from cline CLI: {e}")

    def wait_for_exit():
        global active_cline_process
        return_code = proc.wait()
        stdout_text = "".join(stdout_accumulator)
        stderr_text = "".join(stderr_accumulator)
        
        with active_cline_lock:
            if active_cline_process == proc:
                active_cline_process = None

        add_log_entry("system", f"--- Cline CLI process finished with exit code {return_code} ---")
        logger.info(f"Cline CLI finished with exit code {return_code}")
        if on_complete:
            try:
                on_complete(return_code, stdout_text, stderr_text)
            except Exception as e:
                logger.error(f"Error in on_complete callback: {e}")

    t_out = threading.Thread(target=stream_stdout, daemon=True)
    t_err = threading.Thread(target=stream_stderr, daemon=True)
    t_wait = threading.Thread(target=wait_for_exit, daemon=True)

    t_out.start()
    t_err.start()
    t_wait.start()

    return proc

def terminate_active_cline():
    """
    Terminates the currently active Cline CLI process if running.
    """
    global active_cline_process
    with active_cline_lock:
        if active_cline_process and active_cline_process.poll() is None:
            logger.info("Terminating active Cline CLI process...")
            add_log_entry("system", "--- Terminating active Cline CLI process by user request ---")
            try:
                active_cline_process.terminate()
                time.sleep(0.5)
                if active_cline_process.poll() is None:
                    active_cline_process.kill()
            except Exception as e:
                logger.error(f"Failed to kill Cline CLI process: {e}")
            active_cline_process = None