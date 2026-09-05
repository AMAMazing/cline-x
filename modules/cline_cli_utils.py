import os
import sys
import shutil
import subprocess
import threading
import logging
import time
import re
import json
from typing import Optional, Callable, Dict, Any, List

logger = logging.getLogger(__name__)

# Suppress auto-updates globally across the Python process
os.environ["CLINE_NO_AUTO_UPDATE"] = "1"
os.environ["CLINE_DISABLE_AUTO_UPDATE"] = "1"
os.environ["DISABLE_AUTO_UPDATE"] = "1"

# Ensure %APPDATA%\npm is universally present in os.environ for both .venv and global environments
if sys.platform.startswith("win"):
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        npm_global_dir = os.path.join(appdata, "npm")
        curr_path = os.environ.get("PATH", "")
        if npm_global_dir.lower() not in curr_path.lower():
            os.environ["PATH"] = npm_global_dir + os.pathsep + curr_path

    # Ensure PATHEXT includes .CMD and .BAT
    pathext = os.environ.get("PATHEXT", "")
    if ".CMD" not in pathext.upper():
        os.environ["PATHEXT"] = pathext + ";.CMD;.BAT"

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

def get_universal_env() -> Dict[str, str]:
    """
    Returns an environment dict ensuring npm global paths, local proxy
    variables, and auto-update suppression are always set, whether executing
    inside a .venv or outside.
    """
    env = os.environ.copy()

    # Suppress Cline CLI 2.18.0 auto-update checks and popup updater terminals
    env["CLINE_NO_AUTO_UPDATE"] = "1"
    env["CLINE_DISABLE_AUTO_UPDATE"] = "1"
    env["DISABLE_AUTO_UPDATE"] = "1"

    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            npm_dir = os.path.join(appdata, "npm")
            curr_p = env.get("PATH", "")
            if npm_dir.lower() not in curr_p.lower():
                env["PATH"] = npm_dir + os.pathsep + curr_p
        pathext = env.get("PATHEXT", "")
        if ".CMD" not in pathext.upper():
            env["PATHEXT"] = pathext + ";.CMD;.BAT"

    # Local proxy configuration
    env["OPENAI_BASE_URL"] = "http://127.0.0.1:3001"
    try:
        from modules.auth_utils import API_KEY
        env["OPENAI_API_KEY"] = API_KEY or "dummy"
    except ImportError:
        env["OPENAI_API_KEY"] = "dummy"

    env["AI_SDK_LOG_WARNINGS"] = "false"
    return env

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

def find_cline_executable() -> str:
    """
    Returns 'cline' as the universal executable name.
    """
    return "cline"

def is_cline_available() -> bool:
    """Checks if cline CLI executable is installed and runnable."""
    if shutil.which("cline"):
        return True

    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            if os.path.exists(os.path.join(appdata, "npm", "cline.cmd")) or \
               os.path.exists(os.path.join(appdata, "npm", "cline.ps1")) or \
               os.path.exists(os.path.join(appdata, "npm", "node_modules", "cline", "package.json")):
                return True

    return bool(get_cline_version())

def get_cline_version(cline_bin: Optional[str] = None, force_refresh: bool = False) -> Optional[str]:
    """
    Detects the installed Cline CLI version string (e.g. '2.18.0').
    Checks global npm package.json first for instant, non-blocking lookup,
    then falls back to 'cline version'.
    Results are cached in-memory unless force_refresh is True.
    """
    global _cached_cline_version
    with _cached_version_lock:
        if _cached_cline_version and not force_refresh:
            return _cached_cline_version

        # 1. Fast, instant check via package.json
        if sys.platform.startswith("win"):
            appdata = os.environ.get("APPDATA", "")
            if appdata:
                pkg_json = os.path.join(appdata, "npm", "node_modules", "cline", "package.json")
                if os.path.isfile(pkg_json):
                    try:
                        with open(pkg_json, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            v = data.get("version")
                            if v:
                                _cached_cline_version = v
                                return _cached_cline_version
                    except Exception:
                        pass

        # 2. CLI fallback
        env = get_universal_env()
        is_windows = sys.platform.startswith("win")
        flags = subprocess.CREATE_NO_WINDOW if is_windows else 0
        bin_name = cline_bin or "cline"

        for ver_cmd in [f"{bin_name} version", f"{bin_name} --version"]:
            try:
                res = subprocess.run(
                    ver_cmd,
                    capture_output=True,
                    text=True,
                    stdin=subprocess.DEVNULL,
                    timeout=5,
                    shell=True,
                    env=env,
                    creationflags=flags
                )
                raw = (res.stdout or res.stderr or "").strip()
                match = re.search(r"(\d+\.\d+\.\d+)", raw)
                if match:
                    _cached_cline_version = match.group(1)
                    return _cached_cline_version
            except Exception as e:
                logger.debug(f"Version check '{ver_cmd}' failed: {e}")

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
    Constructs the clean CLI argument list for invoking Cline.
    Starts simply with 'cline'.
    Only specifies yolo, timeout, cwd, and prompt (model is universally configured).
    """
    bin_path = cline_bin or "cline"
    cmd = [bin_path]

    version = get_cline_version(bin_path)
    is_v3 = bool(version and version.startswith("3."))

    if is_v3:
        try:
            from modules.auth_utils import API_KEY
            api_key = API_KEY or "dummy"
        except ImportError:
            api_key = "dummy"
        cmd.extend(["-P", "openai", "-k", api_key])

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
    Universally functions inside or outside of .venv.
    Suppresses auto-update popups via CLINE_NO_AUTO_UPDATE=1.
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

    add_log_entry("system", "--- Launching Cline CLI task ---")
    add_log_entry("system", f"Directory: {cwd or os.getcwd()}")
    add_log_entry("system", f"Timeout: {effective_timeout}s ({effective_timeout // 60}m)")
    add_log_entry("system", f"Command: {cmd_str}")

    stdout_accumulator: List[str] = []
    stderr_accumulator: List[str] = []

    env = get_universal_env()
    is_windows = sys.platform.startswith("win")

    if visible_terminal and is_windows:
        flags = subprocess.CREATE_NEW_CONSOLE
        proc = subprocess.Popen(
            cmd,
            cwd=cwd if (cwd and os.path.isdir(cwd)) else None,
            creationflags=flags,
            shell=True,
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

    flags = subprocess.CREATE_NO_WINDOW if is_windows else 0

    proc = subprocess.Popen(
        cmd,
        cwd=cwd if (cwd and os.path.isdir(cwd)) else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        shell=is_windows,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
        env=env
    )

    with active_cline_lock:
        active_cline_process = proc

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
    """Terminates the currently active Cline CLI process if running."""
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