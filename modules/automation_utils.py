import logging
from typing import Optional, Callable
from modules.cline_cli_utils import run_cline_cli_process, terminate_active_cline

logger = logging.getLogger(__name__)

def process_optimisewait_message(
    message: str,
    project_path: Optional[str] = None,
    yolo: bool = True,
    visible_terminal: bool = False,
    debug: bool = False,
    on_stdout: Optional[Callable[[str], None]] = None,
    on_stderr: Optional[Callable[[str], None]] = None,
    on_complete: Optional[Callable[[int, str, str], None]] = None
):
    """
    Directly dispatches the prompt message to the Cline CLI subprocess.
    Supports headless background streaming or launching in a dedicated visible console.
    """
    logger.info(f"Dispatching task to Cline CLI: {message[:60]}... (cwd: {project_path}, yolo: {yolo}, visible: {visible_terminal})")
    
    return run_cline_cli_process(
        prompt=message,
        cwd=project_path,
        yolo=yolo,
        visible_terminal=visible_terminal,
        on_stdout_line=on_stdout,
        on_stderr_line=on_stderr,
        on_complete=on_complete
    )