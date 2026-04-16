import time
import logging
from modules.vscode_utils import force_bring_to_front, gw
from optimisewait import optimiseWait

logger = logging.getLogger(__name__)

def focus_and_maximize_window(title_to_find, is_exact_match=False):
    """
    Locates a window by title, brings it to front, and attempts to maximize it.
    Returns the project name if successful, else None.
    """
    if not gw:
        return None

    windows = gw.getWindowsWithTitle(title_to_find)
    if not windows:
        return None

    # For VS Code windows, we want to extract the project name from the title
    win = windows[0]
    raw_title = win.title.replace(" - Visual Studio Code", "").strip()
    if " - " in raw_title:
        parts = raw_title.split(" - ")
        project_name = parts[-1].strip()
    else:
        project_name = raw_title

    try:
        force_bring_to_front(win._hWnd)
        if optimiseWait:
            try:
                optimiseWait('maximize', autopath='linkimages')
            except Exception as e:
                logger.error(f"OptimiseWait maximize failed: {e}")
        return project_name
    except Exception as e:
        logger.error(f"Error focusing window: {e}")
        return None

def wait_for_vscode_window(project_name, timeout_deciseconds=100):
    """
    Polls for a VS Code window matching the project name.
    """
    for _ in range(timeout_deciseconds):
        time.sleep(0.1)
        if gw:
            windows = gw.getWindowsWithTitle(project_name)
            for win in windows:
                if "Visual Studio Code" in win.title:
                    try:
                        force_bring_to_front(win._hWnd)
                        if optimiseWait:
                            optimiseWait('maximize', autopath='linkimages')
                        return True
                    except Exception as e:
                        logger.error(f"Error focusing new window: {e}")
                    break
    return False