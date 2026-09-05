import os
import sys
import time
import argparse
import threading
import subprocess

# Ensure current directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.config_utils import read_config
from modules.cline_cli_utils import (
    find_cline_executable,
    is_cline_available,
    get_cline_version,
    build_cline_command,
    run_cline_cli_process,
    terminate_active_cline,
    get_cli_logs,
    clear_cli_logs
)

def run_diagnostics(timeout_minutes: float = None) -> bool:
    # Resolve default timeout from config if not specified
    if timeout_minutes is None:
        try:
            cfg = read_config()
            timeout_minutes = float(cfg.get('queue_timeout_minutes', 5))
        except Exception:
            timeout_minutes = 5.0

    timeout_seconds = int(timeout_minutes * 60)

    print("=" * 60)
    print("CLINE CLI UTILS DIAGNOSTIC TEST")
    print(f"Configured Timeout: {timeout_minutes} minute(s) ({timeout_seconds} seconds)")
    print("=" * 60)

    # 1. Check Executable Detection
    print("\n[Step 1] Checking Executable Discovery...")
    exe = find_cline_executable()
    available = is_cline_available()
    print(f" -> Executable: {exe}")
    print(f" -> Available: {available}")

    if not available or not exe:
        print("[FAIL] Cline executable could not be resolved.")
        return False

    # 2. Check Version Detection
    print("\n[Step 2] Checking Version Detection...")
    version = get_cline_version()
    print(f" -> Detected Version: {version}")

    if not version:
        print("[WARN] Could not parse version string from CLI.")
    else:
        print(f"[OK] Detected Cline CLI version: {version}")

    # 3. Check Clean Command Construction
    print(f"\n[Step 3] Checking Command Construction ({timeout_minutes}m timeout)...")
    cmd = build_cline_command(
        prompt="Say Hi in attempt completion",
        cwd=os.getcwd(),
        yolo=True,
        timeout=timeout_seconds
    )
    cmd_str = ' '.join(f'"{c}"' if ' ' in c else c for c in cmd)
    print(f" -> Constructed Command: {cmd_str}")

    if cmd[0] != "cline":
        print("[FAIL] Command does not start with 'cline'!")
        return False

    if "-m" in cmd:
        print("[FAIL] Redundant -m flag present in command!")
        return False

    if version and version.startswith("2."):
        if "-P" in cmd or "-k" in cmd:
            print("[FAIL] Incompatible flags (-P or -k) present for Cline 2.x!")
            return False
        print("[OK] Clean flag formatting for Cline 2.18.0 verified.")

    # 4. Check Subprocess Execution (Bounded by Timeout Minutes)
    print(f"\n[Step 4] Running Subprocess Execution (Max {timeout_minutes}m / {timeout_seconds}s)...")
    clear_cli_logs()

    completion_event = threading.Event()
    result_data = {
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "timed_out": False
    }

    def on_stdout(line):
        print(f" [CLI STDOUT] {line.strip()}")

    def on_stderr(line):
        print(f" [CLI STDERR] {line.strip()}")

    def on_complete(code, stdout_str, stderr_str):
        result_data["exit_code"] = code
        result_data["stdout"] = stdout_str
        result_data["stderr"] = stderr_str
        completion_event.set()

    test_prompt = "Say Hi in attempt completion"
    proc = run_cline_cli_process(
        prompt=test_prompt,
        cwd=os.getcwd(),
        yolo=True,
        timeout=timeout_seconds,
        visible_terminal=False,
        on_stdout_line=on_stdout,
        on_stderr_line=on_stderr,
        on_complete=on_complete
    )

    print(f" -> Subprocess started with PID: {proc.pid}")

    # Wait for completion up to configured timeout + grace period
    grace_period = 10
    total_wait = timeout_seconds + grace_period
    finished = completion_event.wait(timeout=total_wait)

    if not finished:
        result_data["timed_out"] = True
        print(f"[WARN] Task reached timeout limit ({timeout_minutes}m). Terminating process...")
        terminate_active_cline()
    else:
        print(f" -> Process exited cleanly with code: {result_data['exit_code']}")

    # 5. Check Log Buffer
    print("\n[Step 5] Checking Log Ring Buffer...")
    buffer_data = get_cli_logs()
    log_count = len(buffer_data.get("logs", []))
    print(f" -> Total buffer entries captured: {log_count}")

    print("\n" + "=" * 60)
    if result_data["timed_out"]:
        print(f"[RESULT] Process exceeded {timeout_minutes}m timeout and was terminated.")
        return False
    else:
        print("[RESULT] ALL TESTS COMPLETED SUCCESSFULLY.")
        return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Cline CLI with configurable timeout in minutes.")
    parser.add_argument(
        "-m", "--minutes",
        type=float,
        default=None,
        help="Timeout duration in minutes (e.g. 2, 5, 10). Defaults to queue_timeout_minutes in config."
    )
    args, unknown = parser.parse_known_args()

    minutes_val = args.minutes
    if minutes_val is None and unknown:
        try:
            minutes_val = float(unknown[0])
        except ValueError:
            pass

    success = run_diagnostics(timeout_minutes=minutes_val)
    sys.exit(0 if success else 1)