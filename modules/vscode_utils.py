import os
import json
import ctypes
import subprocess
import logging
from urllib.parse import unquote
from modules.config_utils import IGNORED_FILE

logger = logging.getLogger(__name__)

# --- Import Window Management ---
try:
    import pygetwindow as gw
except ImportError:
    print("CRITICAL ERROR: 'pygetwindow' is missing.")
    print("Please run: pip install pygetwindow")
    gw = None

def force_bring_to_front(hwnd):
    """
    Forces a window to the foreground by attaching thread inputs.
    Bypasses Windows 'flashing taskbar' restriction.
    """
    try:
        user32 = ctypes.windll.user32
        
        foreground_hwnd = user32.GetForegroundWindow()
        current_thread_id = user32.GetWindowThreadProcessId(foreground_hwnd, None)
        target_thread_id = user32.GetWindowThreadProcessId(hwnd, None)
        
        if current_thread_id != target_thread_id:
            user32.AttachThreadInput(current_thread_id, target_thread_id, True)
        
        user32.ShowWindow(hwnd, 9) 
        user32.SetForegroundWindow(hwnd)
        
        if current_thread_id != target_thread_id:
            user32.AttachThreadInput(current_thread_id, target_thread_id, False)
            
    except Exception as e:
        logger.error(f"Force focus failed: {e}")

def load_ignored_folders():
    if os.path.exists(IGNORED_FILE):
        try:
            with open(IGNORED_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []

def save_ignored_folder(path):
    current_ignored = load_ignored_folders()
    if path not in current_ignored:
        current_ignored.append(path)
        try:
            with open(IGNORED_FILE, 'w') as f:
                json.dump(current_ignored, f, indent=4)
        except IOError as e:
            logger.error(f"Failed to save ignored folder: {e}")

def find_vscode_executable():
    appdata_path = os.environ.get('LOCALAPPDATA', '')
    program_files = os.environ.get('ProgramFiles', '')
    program_files_x86 = os.environ.get('ProgramFiles(x86)', '')
    possible_paths = [
        os.path.join(appdata_path, 'Programs', 'Microsoft VS Code', 'Code.exe'),
        os.path.join(appdata_path, 'Programs', 'Microsoft VS Code', 'bin', 'code.cmd'),
        os.path.join(program_files, 'Microsoft VS Code', 'Code.exe'),
        os.path.join(program_files, 'Microsoft VS Code', 'bin', 'code.cmd'),
    ]
    if program_files_x86:
        possible_paths.extend([
            os.path.join(program_files_x86, 'Microsoft VS Code', 'Code.exe'),
            os.path.join(program_files_x86, 'Microsoft VS Code', 'bin', 'code.cmd'),
        ])
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    try:
        result = subprocess.run(['where', 'code'], capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        first_path = result.stdout.strip().splitlines()[0]
        if os.path.exists(first_path):
            return first_path
    except Exception:
        pass
    return None

def get_vscode_projects():
    try:
        possible_paths = [
            os.path.join(os.environ.get('APPDATA', ''), 'Code', 'User', 'globalStorage', 'storage.json'),
            os.path.join(os.environ.get('APPDATA', ''), 'Code - Insiders', 'User', 'globalStorage', 'storage.json'),
            os.path.join(os.environ.get('APPDATA', ''), 'VSCodium', 'User', 'globalStorage', 'storage.json')
        ]
        storage_path = None
        for path in possible_paths:
            if os.path.exists(path):
                storage_path = path
                break
        if not storage_path:
            return []
        with open(storage_path, 'r', encoding='utf-8') as f:
            storage_data = json.load(f)
        project_uris = list(storage_data.get('profileAssociations', {}).get('workspaces', {}).keys())
        cleaned_paths = []
        for uri in project_uris:
            if uri.startswith('file:///'):
                path = unquote(uri[8:]).replace('/', '\\')
                cleaned_paths.append(path)
        folder_paths = [p for p in cleaned_paths if os.path.isdir(p)]
        return sorted(folder_paths, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
    except Exception as e:
        logger.error(f"Error getting projects: {e}")
        return []

def find_project_icon(project_path):
    try:
        if not os.path.isdir(project_path):
            return None
        for item in os.listdir(project_path):
            if item.lower().endswith('.ico'):
                return os.path.join(project_path, item)
    except Exception as e:
        logger.error(f"Error looking for icon in {project_path}: {e}")
    return None

def get_active_windows():
    active_list = []
    if not gw:
        return active_list
    vscode_identifier = " - Visual Studio Code"
    try:
        all_windows = gw.getAllWindows()
        for window in all_windows:
            if window.title and window.title.endswith(vscode_identifier) and window.visible:
                base_name = window.title.removesuffix(vscode_identifier)
                project_name = base_name.split(' - ')[-1].strip()
                active_list.append({
                    'full_title': window.title,
                    'name': project_name
                })
    except Exception as e:
        logger.error(f"Error listing windows: {e}")
    return active_list