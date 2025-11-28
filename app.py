import os
import json
import subprocess
import logging
import time
import sys
import ctypes # Required for forcing window focus
from urllib.parse import unquote
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, abort
from flask_wtf.csrf import CSRFProtect
from waitress import serve
from dotenv import load_dotenv
import pyautogui

# --- Import Window Management ---
try:
    import pygetwindow as gw
except ImportError:
    print("CRITICAL ERROR: 'pygetwindow' is missing.")
    print("Please run: pip install pygetwindow")
    sys.exit(1)

# --- Import Optimisewait ---
try:
    # Attempting to import the function as requested
    from optimisewait import optimiseWait
except ImportError:
    optimisewait = None
    print("WARNING: 'optimisewait' package not found or function not importable. Messaging feature will be limited.")

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)
csrf = CSRFProtect(app)

logging.basicConfig(filename='launcher.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filemode='w')

IGNORED_FILE = 'ignored_folders.json'

# --- Advanced Windows Focus Logic ---
def force_bring_to_front(hwnd):
    """
    Forces a window to the foreground by attaching thread inputs.
    Bypasses Windows 'flashing taskbar' restriction.
    """
    try:
        user32 = ctypes.windll.user32
        
        # 1. Get the thread ID of the current foreground window (likely Chrome)
        foreground_hwnd = user32.GetForegroundWindow()
        current_thread_id = user32.GetWindowThreadProcessId(foreground_hwnd, None)
        
        # 2. Get the thread ID of the target window (VS Code)
        target_thread_id = user32.GetWindowThreadProcessId(hwnd, None)
        
        # 3. Attach threads: Tricks Windows into thinking they share input
        if current_thread_id != target_thread_id:
            user32.AttachThreadInput(current_thread_id, target_thread_id, True)
        
        # 4. Restore if minimized (SW_RESTORE = 9) and bring to front
        user32.ShowWindow(hwnd, 9) 
        user32.SetForegroundWindow(hwnd)
        
        # 5. Detach threads
        if current_thread_id != target_thread_id:
            user32.AttachThreadInput(current_thread_id, target_thread_id, False)
            
    except Exception as e:
        logging.error(f"Force focus failed: {e}")

# --- Helper Functions ---

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
            logging.error(f"Failed to save ignored folder: {e}")

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
            os.path.join(os.environ['APPDATA'], 'Code', 'User', 'globalStorage', 'storage.json'),
            os.path.join(os.environ['APPDATA'], 'Code - Insiders', 'User', 'globalStorage', 'storage.json'),
            os.path.join(os.environ['APPDATA'], 'VSCodium', 'User', 'globalStorage', 'storage.json')
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
                path = unquote(uri[8:]).replace('/', '\\\\')
                cleaned_paths.append(path)
        folder_paths = [p for p in cleaned_paths if os.path.isdir(p)]
        return sorted(folder_paths, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
    except Exception as e:
        logging.error(f"Error getting projects: {e}")
        return []

def find_project_icon(project_path):
    try:
        if not os.path.isdir(project_path):
            return None
        for item in os.listdir(project_path):
            # Strict .ico only
            if item.lower().endswith('.ico'):
                return os.path.join(project_path, item)
    except Exception as e:
        logging.error(f"Error looking for icon in {project_path}: {e}")
    return None

def get_active_windows():
    active_list = []
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
        logging.error(f"Error listing windows: {e}")
    return active_list

# --- Messaging Logic ---
def process_optimisewait_message(message):
    """
    Simple function to handle the message and run optimisewait.
    """
    # maximize line removed as requested
    optimiseWait('newchat', autopath='linkimages')
    optimiseWait('taskhere', autopath='linkimages')
    pyautogui.typewrite(message)
    pyautogui.press('enter')

# --- Routes ---

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember = request.form.get('remember')  # Checkbox value
        
        if username == os.getenv('APP_USERNAME') and password == os.getenv('APP_PASSWORD'):
            session['username'] = username
            if remember:
                session.permanent = True
            else:
                session.permanent = False
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    all_projects = get_vscode_projects()
    ignored_folders = load_ignored_folders()
    
    visible_projects = [p for p in all_projects if p not in ignored_folders]
    active_windows = get_active_windows()
    
    projects_data = []
    for p in visible_projects:
        projects_data.append({
            'path': p,
            'name': os.path.basename(p),
            'has_icon': find_project_icon(p) is not None
        })

    for win in active_windows:
        win['has_icon'] = False
        win['path'] = "" 
        matched_proj = next((p for p in all_projects if os.path.basename(p) == win['name']), None)
        if matched_proj:
            win['path'] = matched_proj
            if find_project_icon(matched_proj):
                win['has_icon'] = True

    return render_template('dashboard.html', projects=projects_data, active_windows=active_windows)

@app.route('/chat')
def chat():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    project_name = request.args.get('project', 'Project')
    return render_template('chat.html', project_name=project_name)

@app.route('/api/active')
def api_active():
    if 'username' not in session:
        return jsonify([])
    
    active_windows = get_active_windows()
    all_projects = get_vscode_projects()
    
    for win in active_windows:
        win['has_icon'] = False
        win['path'] = "" 
        matched_proj = next((p for p in all_projects if os.path.basename(p) == win['name']), None)
        if matched_proj:
            win['path'] = matched_proj
            if find_project_icon(matched_proj):
                win['has_icon'] = True
    
    return jsonify(active_windows)

@app.route('/get_icon')
def get_icon():
    if 'username' not in session:
        return abort(401)
    project_path = request.args.get('path')
    if not project_path:
        return abort(404)
    icon_path = find_project_icon(project_path)
    if icon_path and os.path.exists(icon_path):
        return send_file(icon_path, mimetype='image/x-icon')
    return abort(404)

@app.route('/launch', methods=['POST'])
def launch():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    project_path = request.json.get('path')
    vscode_exe = find_vscode_executable()
    
    if vscode_exe and project_path and os.path.isdir(project_path):
        try:
            # 1. Launch the process
            subprocess.Popen([vscode_exe, project_path], creationflags=subprocess.CREATE_NO_WINDOW)
            
            project_name = os.path.basename(project_path)
            
            # 2. Sync Wait for window to appear
            # We block here so the frontend shows "Processing..." until we are ready
            found_window = False
            
            # Poll for up to 10 seconds (100 checks * 0.1s)
            # Faster polling for better speed perception
            for i in range(100): 
                time.sleep(0.1) 
                windows = gw.getWindowsWithTitle(project_name)
                for win in windows:
                    if "Visual Studio Code" in win.title:
                        # Found it! Force focus.
                        try:
                            force_bring_to_front(win._hWnd)
                            found_window = True
                        except Exception as e:
                            logging.error(f"Error focusing new window: {e}")
                        break
                if found_window:
                    break
            
            # 3. Run optimiseWait('maximize') last
            if optimiseWait:
                try:
                    optimiseWait('maximize', autopath='linkimages')
                except Exception as e:
                    logging.error(f"OptimiseWait maximize failed: {e}")

            # Only returns after everything is done
            return jsonify({'status': 'success', 'message': 'Opening...', 'project_name': project_name})
            
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
            
    return jsonify({'status': 'error', 'message': 'Invalid path'}), 400

@app.route('/focus', methods=['POST'])
def focus():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    title_to_find = request.json.get('title')
    
    try:
        windows = gw.getWindowsWithTitle(title_to_find)
        if windows:
            win = windows[0]
            project_name = win.title.replace(" - Visual Studio Code", "").strip()

            # --- Force Focus Sync ---
            force_bring_to_front(win._hWnd)
            
            # --- OptimiseWait Sync ---
            if optimiseWait:
                try:
                    optimiseWait('maximize', autopath='linkimages')
                except Exception as e:
                    logging.error(f"OptimiseWait maximize failed: {e}")
            
            # Returns only after done
            return jsonify({'status': 'success', 'message': 'Focused', 'project_name': project_name})
        else:
            return jsonify({'status': 'error', 'message': 'Window not found'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/send_message', methods=['POST'])
def send_message():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    
    data = request.json
    message = data.get('message')
    
    if not message:
        return jsonify({'status': 'error', 'message': 'Message cannot be empty'}), 400

    try:
        process_optimisewait_message(message)
        return jsonify({'status': 'success', 'message': 'Message processed'})
    except Exception as e:
        logging.error(f"Message processing failed: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/ignore', methods=['POST'])
def ignore_project():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    project_path = request.json.get('path')
    if project_path:
        save_ignored_folder(project_path)
        return jsonify({'status': 'success', 'message': 'Project ignored'})
    return jsonify({'status': 'error', 'message': 'Invalid path'}), 400

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    print("Server starting on http://127.0.0.1:5000")
    serve(app, host='127.0.0.1', port=5000)
