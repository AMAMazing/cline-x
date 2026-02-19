from flask import Flask, jsonify, request, Response, abort, render_template, redirect, url_for, session, send_file
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import webbrowser
import win32clipboard
import time
import pywintypes
from time import sleep
import os
import ctypes
from urllib.parse import unquote
from optimisewait import optimiseWait, set_autopath, set_altpath
import pyautogui
import logging
import json
from threading import Timer
import threading
from typing import Union, List, Dict, Optional
import base64
import io
from PIL import Image
import re
from talktollm import talkto
import requests
import secrets
import string
from functools import wraps
from pyngrok import ngrok
import sys
from dotenv import load_dotenv, set_key
import colorama
from ascii import art as attempt_completion_art
from ascii import banner as bannertop
import subprocess
from datetime import timedelta

# Fix for Windows Unicode Output
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass # Older python versions might not support this

# --- Import Window Management (from app.py) ---
try:
    import pygetwindow as gw
except ImportError:
    print("CRITICAL ERROR: 'pygetwindow' is missing.")
    print("Please run: pip install pygetwindow")
    # We continue but features will fail
    gw = None

# --- PATH HANDLING for frozen executables ---
def get_app_path():
    """Get the appropriate path for the application's data files."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

APP_PATH = get_app_path()
DOTENV_PATH = os.path.join(APP_PATH, '.env')
IGNORED_FILE = 'ignored_folders.json' # From app.py

load_dotenv(dotenv_path=DOTENV_PATH)

# --- CONFIGURATION HANDLING ---
def get_config_path():
    return os.path.join(APP_PATH, "clinex_config.json")

def read_config():
    """Reads the configuration file and returns a dictionary."""
    config = {}
    config_path = get_config_path()
    
    # Fallback to old config.txt if json doesn't exist
    old_config_path = os.path.join(APP_PATH, "config.txt")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except Exception as e:
            print(f"Error reading clinex_config.json: {e}")

    elif os.path.exists(old_config_path):
        try:
            with open(old_config_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip().strip('"').strip("'")
            # Migrate to JSON? Optional.
        except Exception:
            pass
            
    # Set defaults if missing
    defaults = {
        'model': 'gemini',
        'theme': 'dark',
        'ntfy_topic': '',
        'ntfy_notification_level': 'none',
        'terminal_log_level': 'default',
        'terminal_alert_level': 'none',
        'tunnel_active': 'False',
        'auth_required': 'False'
    }
    
    for k, v in defaults.items():
        if k not in config:
            config[k] = v
            
    return config

def write_config(config_data):
    """Writes the configuration dictionary to the specified file."""
    # Always write to JSON now
    with open(get_config_path(), 'w') as f:
        json.dump(config_data, f, indent=4)

def get_rules_content():
    """Reads the unified rules from an external file."""
    rules_path = os.path.join(APP_PATH, "unified_rules.txt")
    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"ERROR: '{rules_path}' not found. Please create this file with your system prompt.")
        return "You are a helpful AI assistant." # Fallback if file is missing
    except Exception as e:
        print(f"ERROR reading rules file: {e}")
        return "You are a helpful AI assistant."

# Load initial configuration
config = read_config()
current_model = config.get('model', 'gemini')
current_theme = config.get('theme', 'dark')
ntfy_notification_level = config.get('ntfy_notification_level', 'none')
terminal_log_level = config.get('terminal_log_level', 'default')
terminal_alert_level = config.get('terminal_alert_level', 'none')
tunnel_active = str(config.get('tunnel_active', 'False')).lower() == 'true'
auth_required = str(config.get('auth_required', 'False')).lower() == 'true'

# --- LOGGING SETUP ---
class CustomFormatter(logging.Formatter):
    """Custom formatter that respects terminal_log_level"""
    def format(self, record):
        if terminal_log_level == 'none':
            return ''
        elif terminal_log_level == 'minimal':
            # Only show specific messages in a simple format
            if 'Starting' in record.msg or 'notification' in record.msg.lower():
                # Remove timestamps and level for minimal
                if 'Starting' in record.msg:
                    return f"Starting {current_model.upper()} interaction"
                elif 'Successfully sent' in record.msg:
                    return "Sent notification"
                return ''
            return ''
        elif terminal_log_level == 'debug':
            # Show everything including debug messages
            return super().format(record)
        else:  # default
            # Standard INFO level formatting
            if record.levelno >= logging.INFO:
                return super().format(record)
            return ''

# Setup logging with custom formatter
handler = logging.StreamHandler()
handler.setFormatter(CustomFormatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG if terminal_log_level == 'debug' else logging.INFO)

# --- State for clearing the alert ---
alert_lines_printed = 0
alert_active = False

# --- Chat History for Web Interface ---
chat_history = []
MAX_CHAT_HISTORY = 50

def add_chat_message(role, text):
    global chat_history
    message = {'role': role, 'text': text, 'time': time.strftime('%H:%M')}
    chat_history.append(message)
    if len(chat_history) > MAX_CHAT_HISTORY:
        chat_history.pop(0)

# --- API Key (only used when auth_required is True) ---
API_KEY = secrets.token_urlsafe(32)

def require_api_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Check if Auth is required in config
        current_auth_required = str(config.get('auth_required', 'False')).lower() == 'true'
        if not current_auth_required:
            return func(*args, **kwargs)
            
        # 1. Check Header
        if request.headers.get('X-API-Key') == API_KEY or request.headers.get('Authorization', '').replace('Bearer ', '') == API_KEY:
            return func(*args, **kwargs)
            
        # 2. Check Query String (Magic Link)
        if request.args.get('api_key') == API_KEY:
             return func(*args, **kwargs)
             
        abort(401, description="Invalid or missing API key")
    return wrapper

app = Flask(__name__)
app.secret_key = os.urandom(24) # Ensure secret key for session
# app.permanent_session_lifetime is no longer critical without login, but kept for good measure
app.permanent_session_lifetime = timedelta(days=30) 
csrf = CSRFProtect(app) # Enable CSRF protection

# --- RATE LIMITER SETUP ---
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

last_request_time = 0
MIN_REQUEST_INTERVAL = 5

set_autopath(r"D:\cline-x-claudeweb\images")
set_altpath(r"D:\cline-x-claudeweb\images\alt1440")

# --- HELPER FUNCTIONS FROM APP.PY ---

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
            # Strict .ico only
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

def process_optimisewait_message(message):
    """
    Simple function to handle the message and run optimisewait.
    """
    # maximize line removed as requested
    optimiseWait('newchat', autopath='linkimages')
    optimiseWait('taskhere', autopath='linkimages')
    
    # Use the existing set_clipboard helper from your code
    set_clipboard(message)
    
    # Short sleep to ensure clipboard system is ready (optional but recommended)
    time.sleep(0.1)
    
    # Paste and Enter
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.1) 
    pyautogui.press('enter')


# --- NTFY NOTIFICATION ---
def send_ntfy_notification(topic: str, simple_title: str, full_content: str, tags: str = "tada"):
    """Sends a push notification via ntfy.sh and adds to local chat history"""
    
    # Add to local chat history for Cline Link
    add_chat_message('system', f"{simple_title}: {full_content}")

    if not topic:
        logger.debug("ntfy_topic not configured. Skipping notification.")
        return

    # Handle topic vs full URL
    target_url = topic
    if not target_url.startswith("http"):
        target_url = f"https://ntfy.sh/{target_url}"

    try:
        response = requests.post(
            target_url,
            data=full_content.encode('utf-8'),
            headers={
                "Title": simple_title.encode('utf-8'),
                "Priority": "high",
                "Tags": tags
            }
        )
        response.raise_for_status()
        logger.info(f"Successfully sent ntfy notification to topic: {topic}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send ntfy notification: {e}")

# --- CLIPBOARD FUNCTIONS ---
def set_clipboard(text, retries=3, delay=0.2):
    for i in range(retries):
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            try:
                win32clipboard.SetClipboardText(str(text))
            except Exception:
                win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, str(text).encode('utf-16le'))
            win32clipboard.CloseClipboard()
            return
        except pywintypes.error as e:
            if e.winerror == 5:
                if terminal_log_level == 'debug':
                    print(f"Clipboard access denied. Retrying... (Attempt {i+1}/{retries})")
                time.sleep(delay)
            else:
                raise
        except Exception as e:
            raise
    if terminal_log_level == 'debug':
        print(f"Failed to set clipboard after {retries} attempts.")

def set_clipboard_image(image_data):
    try:
        binary_data = base64.b64decode(image_data.split(',')[1])
        image = Image.open(io.BytesIO(binary_data))
        output = io.BytesIO()
        image.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]
        output.close()
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        if terminal_log_level == 'debug':
            print(f"Error setting image to clipboard: {e}")
        return False

# --- ALERT CLEARING FUNCTIONS ---
def clear_previous_alert():
    """Clear any previous alert from the terminal using multiple methods."""
    global alert_lines_printed, alert_active
    
    if not alert_active or alert_lines_printed <= 0:
        return
    
    try:
        if os.name == 'nt':
            sys.stdout.write(f"\033[{alert_lines_printed}A")
            sys.stdout.write("\033[J")
        else:
            sys.stdout.write(f"\x1b[{alert_lines_printed}A")
            sys.stdout.write("\x1b[J")
        sys.stdout.flush()
    except Exception:
        try:
            terminal_height = os.get_terminal_size().lines
            print("\n" * min(alert_lines_printed + 5, terminal_height))
        except Exception:
            print("\n" * (alert_lines_printed + 3))
    
    alert_lines_printed = 0
    alert_active = False

def print_completion_alert():
    """Prints a completion alert and tracks it for later clearing."""
    global alert_lines_printed, alert_active
    
    clear_previous_alert()
    
    border_char = "#"
    border_width = 80
    border_top = colorama.Fore.YELLOW + colorama.Style.BRIGHT + (border_char * border_width)
    border_bottom = colorama.Fore.YELLOW + colorama.Style.BRIGHT + (border_char * border_width)
    colored_art = colorama.Fore.GREEN + colorama.Style.BRIGHT + attempt_completion_art + colorama.Style.RESET_ALL
    
    alert_lines = [
        "",
        border_top,
        *colored_art.strip().split('\n'),
        border_bottom,
        ""
    ]
    
    alert_lines_printed = len(alert_lines)
    alert_active = True
    
    for line in alert_lines:
        print(line)
    
    sys.stdout.flush()

def print_summary_alert(summary: str):
    """Prints a summary message in a highlighted format."""
    global alert_lines_printed, alert_active
    
    # Also add to chat history
    add_chat_message('system', f"AI Summary: {summary}")
    
    # Don't clear previous alert for summaries, just print below
    
    border = colorama.Fore.CYAN + colorama.Style.BRIGHT + "=" * 60
    title = colorama.Fore.CYAN + colorama.Style.BRIGHT + "[INFO] AI Summary:"
    content = colorama.Fore.WHITE + colorama.Style.BRIGHT + summary
    
    alert_message = [
        "",
        border,
        title,
        content,
        border,
        ""
    ]
    
    for line in alert_message:
        print(line)
    
    sys.stdout.flush()

# --- CORE LOGIC ---
def get_content_text(content: Union[str, List[Dict[str, str]], Dict[str, str]]) -> str:
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        parts = []
        for item in content:
            if item.get("type") == "text":
                parts.append(item["text"])
            elif item.get("type") == "image_url":
                image_data = item.get("image_url", {}).get("url", "")
                if image_data.startswith('data:image'):
                    set_clipboard_image(image_data)
                parts.append(f"[Image: An uploaded image]")
        return "\n".join(parts)
    return ""

def handle_llm_interaction(prompt):
    global last_request_time
    clear_previous_alert()
    
    logger.info(f"Starting {current_model} interaction.")

    current_time = time.time()
    time_since_last = current_time - last_request_time
    if time_since_last < MIN_REQUEST_INTERVAL:
        sleep(MIN_REQUEST_INTERVAL - time_since_last)
    last_request_time = time.time()

    request_json = request.get_json()
    image_list = []
    
    if 'messages' in request_json:
        for message in request_json['messages']:
            content = message.get('content', [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'image_url':
                        image_url = item.get('image_url', {}).get("url", '')
                        if image_url.startswith('data:image'):
                            image_list.append(image_url)

    # This is what gets sent to the LLM
    current_time_str = time.strftime('%Y-%m-%d %H:%M:%S')
    headers_log = f"{current_time_str} - INFO - Request data: {json.dumps(request_json)}"

    # --- UNIFIED PROMPT RULES ---
    # Now loaded from external file
    unified_rules = get_rules_content()

    # Start building instructions list
    prompt_instructions = [headers_log]

    # Enable summary if terminal_alert_level is 'all' OR ntfy is 'all'
    if terminal_alert_level == 'all' or ntfy_notification_level == 'all':
        summary_instruction = r"You MUST include a `<summary>` tag inside your `<thinking>` block for every tool call. This summary should be a very brief, user-friendly explanation of the action you are about to take. For example: `<summary>Reading the project's configuration to check dependencies.</summary>`."
        prompt_instructions.append(summary_instruction)

    # Add the actual user message/prompt
    prompt_instructions.append(prompt)

    # Add the unified rules LAST (before the prompt) so they have highest priority
    prompt_instructions.append(unified_rules)
    
    fullpromptbefore = "\n".join(prompt_instructions)

    full_prompt = re.sub(r'data:image\/png;base64,[A-Za-z0-9+\/=]+', '', fullpromptbefore)

    debug_mode = (terminal_log_level == 'debug')
    return talkto(current_model, full_prompt, image_list, debug=debug_mode)


# --- FLASK ROUTES ---
@app.route('/', methods=['GET'])
def home():
    logger.debug(f"GET request to / from {request.remote_addr}")
    
    # Gather context for the control panel template
    public_url = ngrok_tunnel.public_url if 'ngrok_tunnel' in globals() else 'Starting...'
    
    return render_template('control_panel.html',
                           current_model=current_model,
                           terminal_log_level=terminal_log_level,
                           terminal_alert_level=terminal_alert_level,
                           ntfy_notification_level=ntfy_notification_level,
                           config=config,
                           tunnel_active=tunnel_active,
                           auth_required=auth_required,
                           public_url=public_url,
                           api_key=API_KEY)

@app.route('/model', methods=['GET', 'POST'])
def model_route():
    global current_model, config
    if request.method == 'GET':
        return jsonify({'model': current_model})
    
    if request.method == 'POST':
        try:
            clear_previous_alert()
            data = request.get_json()
            new_model = data['model'].lower()
            if new_model not in ['deepseek', 'gemini', 'aistudio']:
                return jsonify({'success': False, 'error': 'Invalid model'}), 400
            current_model = new_model
            config['model'] = current_model
            write_config(config)
            logger.info(f"Model switched to: {current_model}")
            return jsonify({'success': True, 'model': current_model})
        except Exception as e:
            logger.error(f"Error switching model: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/notifications', methods=['POST'])
def notification_settings():
    global ntfy_notification_level, config
    try:
        data = request.get_json()
        if data is None or 'level' not in data:
            return jsonify({'success': False, 'error': 'Invalid request'}), 400
        
        new_level = data['level'].lower()
        if new_level not in ['none', 'completion', 'all']:
            return jsonify({'success': False, 'error': 'Invalid level'}), 400

        ntfy_notification_level = new_level
        config['ntfy_notification_level'] = ntfy_notification_level
        write_config(config)
        logger.info(f"Notification level set to: {ntfy_notification_level}")
        return jsonify({'success': True, 'level': ntfy_notification_level})
    except Exception as e:
        logger.error(f"Error setting notification level: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/notifications/enable', methods=['POST'])
def enable_ntfy():
    global config
    try:
        # Generate a random topic code (shorter)
        random_code = secrets.token_urlsafe(10) # Was 12
        topic = f"clinex-{random_code}" # Just the topic, no https://ntfy.sh/
        
        config['ntfy_topic'] = topic
        write_config(config)
        logger.info(f"Generated ntfy topic: {topic}")
        return jsonify({'success': True, 'topic': topic})
    except Exception as e:
        logger.error(f"Error enabling ntfy: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/log-level', methods=['POST'])
def set_log_level():
    global terminal_log_level, config
    try:
        data = request.get_json()
        if data is None or 'level' not in data:
            return jsonify({'success': False, 'error': 'Invalid request'}), 400
        
        new_level = data['level'].lower()
        if new_level not in ['none', 'minimal', 'default', 'debug']:
            return jsonify({'success': False, 'error': 'Invalid level'}), 400

        terminal_log_level = new_level
        config['terminal_log_level'] = terminal_log_level
        write_config(config)
        
        # Update logger level
        if new_level == 'debug':
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
        
        logger.info(f"Terminal log level set to: {terminal_log_level}")
        return jsonify({'success': True, 'level': terminal_log_level})
    except Exception as e:
        logger.error(f"Error setting log level: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/alert-level', methods=['POST'])
def set_alert_level():
    global terminal_alert_level, config
    try:
        data = request.get_json()
        if data is None or 'level' not in data:
            return jsonify({'success': False, 'error': 'Invalid request'}), 400
        
        new_level = data['level'].lower()
        if new_level not in ['none', 'completions', 'all']:
            return jsonify({'success': False, 'error': 'Invalid level'}), 400

        terminal_alert_level = new_level
        config['terminal_alert_level'] = terminal_alert_level
        write_config(config)
        logger.info(f"Terminal alert level set to: {terminal_alert_level}")
        return jsonify({'success': True, 'level': terminal_alert_level})
    except Exception as e:
        logger.error(f"Error setting alert level: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/remote/tunnel', methods=['POST'])
@limiter.limit("5 per minute")
def toggle_tunnel():
    global tunnel_active, config, ngrok_tunnel
    try:
        data = request.get_json()
        if data is None or 'enabled' not in data:
            return jsonify({'success': False, 'error': 'Invalid request'}), 400

        new_state = data['enabled']
        
        if new_state and not tunnel_active:
            # Enabling tunnel - start ngrok
            ngrok_authtoken = os.getenv("NGROK_AUTHTOKEN")
            if not ngrok_authtoken:
                return jsonify({'success': False, 'error': 'NGROK_AUTHTOKEN not found in .env'}), 400
            
            try:
                ngrok.set_auth_token(ngrok_authtoken)
                # Check for persistent domain env var
                ngrok_domain = os.getenv("NGROK_DOMAIN")
                if ngrok_domain:
                    ngrok_tunnel = ngrok.connect(3001, domain=ngrok_domain)
                else:
                    ngrok_tunnel = ngrok.connect(3001)

                tunnel_active = True
                logger.info(f"ngrok tunnel established: {ngrok_tunnel.public_url}")
                
                # Send ntfy notification
                ntfy_topic = config.get('ntfy_topic', '')
                if ntfy_topic:
                    public_url = ngrok_tunnel.public_url
                    current_auth = str(config.get('auth_required', 'False')).lower() == 'true'
                    if current_auth:
                        # Append Magic Link query param
                        public_url += f"/?api_key={API_KEY}"
                        
                    send_ntfy_notification(
                        topic=ntfy_topic,
                        simple_title="Cline-X: Remote Tunnel Active",
                        full_content=f"Your remote access tunnel is ready: {public_url}",
                        tags="rocket"
                    )

            except Exception as e:
                logger.error(f"Failed to start ngrok: {e}")
                return jsonify({'success': False, 'error': f'Failed to start ngrok: {str(e)}'}), 500
                
        elif not new_state and tunnel_active:
            # Disabling tunnel - stop ngrok
            try:
                if 'ngrok_tunnel' in globals():
                    ngrok.disconnect(ngrok_tunnel.public_url)
                tunnel_active = False
                logger.info("ngrok tunnel disconnected")
            except Exception as e:
                logger.error(f"Failed to stop ngrok: {e}")
                # Continue anyway since we're disabling
                tunnel_active = False
        
        config['tunnel_active'] = str(tunnel_active)
        write_config(config)
        
        response_data = {'success': True, 'enabled': tunnel_active}
        if tunnel_active and 'ngrok_tunnel' in globals():
            response_data['public_url'] = ngrok_tunnel.public_url
            response_data['api_key'] = API_KEY
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error toggling tunnel: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/remote/auth', methods=['POST'])
@limiter.limit("5 per minute")
def toggle_auth():
    global auth_required, config
    try:
        data = request.get_json()
        if data is None or 'enabled' not in data:
            return jsonify({'success': False, 'error': 'Invalid request'}), 400

        new_state = data['enabled']
        auth_required = new_state
        config['auth_required'] = str(auth_required)
        write_config(config)
        
        if auth_required:
             # Send ntfy notification with API Key
            ntfy_topic = config.get('ntfy_topic', '')
            if ntfy_topic:
                send_ntfy_notification(
                    topic=ntfy_topic,
                    simple_title="Cline-X: Auth Enabled",
                    full_content=f"Security enabled. Your API Key is: {API_KEY}",
                    tags="lock"
                )
        
        logger.info(f"Auth requirement set to: {auth_required}")
        return jsonify({'success': True, 'enabled': auth_required, 'api_key': API_KEY})
        
    except Exception as e:
        logger.error(f"Error toggling auth: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/theme', methods=['POST'])
def theme_settings():
    global current_theme, config
    try:
        data = request.get_json()
        if data is None or 'theme' not in data:
            return jsonify({'success': False, 'error': 'Invalid request'}), 400
        
        new_theme = data['theme'].lower()
        if new_theme not in ['light', 'dark']:
            return jsonify({'success': False, 'error': 'Invalid theme'}), 400

        current_theme = new_theme
        config['theme'] = current_theme
        write_config(config)
        logger.info(f"Theme set to: {current_theme}")
        return jsonify({'success': True, 'theme': current_theme})
    except Exception as e:
        logger.error(f"Error setting theme: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/open-rules', methods=['POST'])
def open_rules_file():
    """Generic route to open any local file or folder path."""
    try:
        data = request.json
        path = data.get('path')
        
        if not path or not os.path.exists(path):
            return jsonify({'success': False, 'error': 'Path does not exist'}), 404
        
        # os.startfile is Windows-specific and opens the file in the default app
        os.startfile(path)
        return jsonify({'success': True, 'message': f'Opened {path}'})
    except Exception as e:
        logger.error(f"Failed to open path: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/chat/completions', methods=['POST'])
@require_api_key
@csrf.exempt # Exempt external API from CSRF
@limiter.limit("20 per minute")
def chat_completions():
    try:
        clear_previous_alert()
        
        data = request.get_json()
        if not data or 'messages' not in data:
            return jsonify({'error': {'message': 'Invalid request format'}}), 400

        prompt = get_content_text(data['messages'][-1].get('content', ''))
        
        is_streaming = data.get('stream', False)
        response = handle_llm_interaction(prompt)
        request_id = f'chatcmpl-{int(time.time())}'

        # Check for attempt_completion
        has_completion = "<attempt_completion>" in response
        
        # Extract summary if present
        summary_match = re.search(r"<summary>(.*?)</summary>", response, re.DOTALL)
        summary = summary_match.group(1).strip() if summary_match else None

        # Terminal alerts
        if has_completion and terminal_alert_level in ['completions', 'all']:
            print_completion_alert()
        elif summary and terminal_alert_level == 'all':
            print_summary_alert(summary)

        # ntfy notifications
        ntfy_topic = config.get('ntfy_topic', '')
        if ntfy_notification_level == 'all':
            if has_completion:
                send_ntfy_notification(
                    topic=ntfy_topic,
                    simple_title="Cline-X: Task Completion",
                    full_content=summary or "Task completion submitted.",
                    tags="tada"
                )
            elif summary:
                send_ntfy_notification(
                    topic=ntfy_topic,
                    simple_title="[INFO] Cline-X: AI Response",
                    full_content=summary,
                    tags="robot_face"
                )
        elif ntfy_notification_level == 'completion' and has_completion:
            send_ntfy_notification(
                topic=ntfy_topic,
                simple_title="Cline-X: Task Completion",
                full_content=response,
                tags="tada"
            )
        
        if is_streaming:
            def generate():
                chunk = {"id": request_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": "gpt-3.5-turbo", "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
                yield f"data: {json.dumps(chunk)}\n\n"
                
                lines = response.splitlines(True)
                for line in lines:
                    content_chunk = {"id": request_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": "gpt-3.5-turbo", "choices": [{"index": 0, "delta": {"content": line}, "finish_reason": None}]}
                    yield f"data: {json.dumps(content_chunk)}\n\n"
                
                stop_chunk = {"id": request_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": "gpt-3.5-turbo", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                yield f"data: {json.dumps(stop_chunk)}\n\n"
                yield "data: [DONE]\n\n"
            
            return Response(generate(), mimetype='text/event-stream')

        return jsonify({
            'id': request_id, 'object': 'chat.completion', 'created': int(time.time()),
            'model': 'gpt-3.5-turbo', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': response}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': len(prompt), 'completion_tokens': len(response), 'total_tokens': len(prompt) + len(response)}
        })
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return jsonify({'error': {'message': str(e)}}), 500

# --- APP.PY ROUTES (CLINE LINK) ---

@app.route('/dashboard')
def dashboard():
    # Removed login check as requested
    
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
    # Removed login check
    project_name = request.args.get('project', 'Project')
    return render_template('chat.html', project_name=project_name)

@app.route('/api/active')
def api_active():
    # Removed login check
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

@app.route('/api/screenshot')
def api_screenshot():
    # Removed login check
    try:
        img = pyautogui.screenshot()
        img_io = io.BytesIO()
        img.save(img_io, 'JPEG', quality=70)
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_icon')
def get_icon():
    # Removed login check
    project_path = request.args.get('path')
    if not project_path:
        return abort(404)
    icon_path = find_project_icon(project_path)
    if icon_path and os.path.exists(icon_path):
        return send_file(icon_path, mimetype='image/x-icon')
    return abort(404)

@app.route('/launch', methods=['POST'])
def launch():
    # Removed login check
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
                if gw:
                    windows = gw.getWindowsWithTitle(project_name)
                    for win in windows:
                        if "Visual Studio Code" in win.title:
                            # Found it! Force focus.
                            try:
                                force_bring_to_front(win._hWnd)
                                found_window = True
                            except Exception as e:
                                logger.error(f"Error focusing new window: {e}")
                            break
                if found_window:
                    break
            
            # 3. Run optimiseWait('maximize') last
            if optimiseWait:
                try:
                    optimiseWait('maximize', autopath='linkimages')
                except Exception as e:
                    logger.error(f"OptimiseWait maximize failed: {e}")

            # Only returns after everything is done
            return jsonify({'status': 'success', 'message': 'Opening...', 'project_name': project_name})
            
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
            
    return jsonify({'status': 'error', 'message': 'Invalid path'}), 400

@app.route('/focus', methods=['POST'])
def focus():
    # Removed login check
    title_to_find = request.json.get('title')
    
    try:
        if gw:
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
                        logger.error(f"OptimiseWait maximize failed: {e}")
                
                # Returns only after done
                return jsonify({'status': 'success', 'message': 'Focused', 'project_name': project_name})
        
        return jsonify({'status': 'error', 'message': 'Window not found'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/send_message', methods=['POST'])
@limiter.limit("20 per minute")
def send_message():
    # Removed login check
    
    data = request.json
    message = data.get('message')
    
    if not message:
        return jsonify({'status': 'error', 'message': 'Message cannot be empty'}), 400

    try:
        add_chat_message('user', message) # Add user message to history
        process_optimisewait_message(message)
        return jsonify({'status': 'success', 'message': 'Message processed'})
    except Exception as e:
        logger.error(f"Message processing failed: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/ignore', methods=['POST'])
def ignore_project():
    # Removed login check
    project_path = request.json.get('path')
    if project_path:
        save_ignored_folder(project_path)
        return jsonify({'status': 'success', 'message': 'Project ignored'})
    return jsonify({'status': 'error', 'message': 'Invalid path'}), 400

def terminal_link(path):
    """Creates a clickable link for terminal emulators that support OSC 8."""
    # Convert backslashes to forward slashes for the file:// protocol
    absolute_path = os.path.abspath(path).replace('\\', '/')
    if not absolute_path.startswith('/'):
        absolute_path = '/' + absolute_path
    
    # OSC 8 escape sequence: \033]8;;url\033\text\033]8;;\033\
    return f"\033]8;;file://{absolute_path}\033\\{path}\033]8;;\033\\"

@app.route('/get_messages')
def get_messages():
    """Poll for new messages"""
    # Removed login check
    return jsonify(chat_history)

def print_startup_banner():
    """Print a nice startup banner with all the important information"""
    colorama.init(autoreset=True)
    rules_path = os.path.join(APP_PATH, "unified_rules.txt")
    
    # Replaced emojis with ASCII tags for Windows compatibility
    banner = f"""
{bannertop}

{colorama.Fore.YELLOW + colorama.Style.BRIGHT}[INFO] SERVER INFORMATION:{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Local:  {colorama.Fore.CYAN + colorama.Style.BRIGHT}http://127.0.0.1:3001{colorama.Style.RESET_ALL}"""
    
    if tunnel_active:
        banner += f"""
   {colorama.Fore.WHITE}Remote: {colorama.Fore.GREEN + colorama.Style.BRIGHT}{ngrok_tunnel.public_url if 'ngrok_tunnel' in globals() else 'Starting...'}{colorama.Style.RESET_ALL}"""
    
    if auth_required:
        banner += f"""
   {colorama.Fore.WHITE}API Key: {colorama.Fore.MAGENTA + colorama.Style.BRIGHT}{API_KEY}{colorama.Style.RESET_ALL}"""
    
    clickable_rules_path = terminal_link(rules_path)

    banner += f"""

{colorama.Fore.YELLOW + colorama.Style.BRIGHT}[CONFIG] CURRENT SETTINGS:{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Model: {colorama.Fore.GREEN + colorama.Style.BRIGHT}{current_model.upper()}{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Theme: {colorama.Fore.GREEN + colorama.Style.BRIGHT}{current_theme.capitalize()}{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Terminal Output: {colorama.Fore.GREEN + colorama.Style.BRIGHT}{terminal_log_level.capitalize()}{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Terminal Alerts: {colorama.Fore.GREEN + colorama.Style.BRIGHT}{terminal_alert_level.capitalize()}{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Push Notifications: {colorama.Fore.GREEN + colorama.Style.BRIGHT}{ntfy_notification_level.capitalize()}{colorama.Style.RESET_ALL}

{colorama.Fore.YELLOW + colorama.Style.BRIGHT}[FILES] SYSTEM RULES:{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Unified Rules: {colorama.Fore.CYAN + colorama.Style.BRIGHT}{clickable_rules_path}{colorama.Style.RESET_ALL}
   {colorama.Style.DIM}(Ctrl+Click the path above to edit rules directly){colorama.Style.RESET_ALL}

{colorama.Fore.YELLOW + colorama.Style.BRIGHT}[PANEL] CONTROL PANEL:{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Open your browser and go to:{colorama.Style.RESET_ALL}
   {colorama.Fore.CYAN + colorama.Style.BRIGHT + colorama.Back.BLACK}  http://127.0.0.1:3001  {colorama.Style.RESET_ALL}
   
   {colorama.Fore.WHITE}Tip: Use the 'Open Rules in Editor' button in the dashboard for quick access!{colorama.Style.RESET_ALL}

{colorama.Fore.CYAN + colorama.Style.BRIGHT}{'=' * 62}{colorama.Style.RESET_ALL}
"""
    print(banner)

if __name__ == '__main__':
    colorama.init(autoreset=True)

    # Handle ngrok setup if remote is enabled
    if tunnel_active:
        ngrok_authtoken = os.getenv("NGROK_AUTHTOKEN")
        if not ngrok_authtoken:
            print(f"{colorama.Fore.RED}NGROK_AUTHTOKEN not found in .env file.{colorama.Style.RESET_ALL}")
            ngrok_authtoken = input("Please enter your ngrok authtoken: ").strip()
            if ngrok_authtoken:
                set_key(DOTENV_PATH, "NGROK_AUTHTOKEN", ngrok_authtoken)
                print(f"{colorama.Fore.GREEN}NGROK_AUTHTOKEN saved to {DOTENV_PATH} for future use.{colorama.Style.RESET_ALL}")
            else:
                logger.error("No NGROK_AUTHTOKEN provided. Exiting.")
                exit()
        try:
            ngrok.set_auth_token(ngrok_authtoken)
            # Check for persistent domain env var
            ngrok_domain = os.getenv("NGROK_DOMAIN")
            if ngrok_domain:
                ngrok_tunnel = ngrok.connect(3001, domain=ngrok_domain)
            else:
                ngrok_tunnel = ngrok.connect(3001)

            logger.info(f"ngrok tunnel established: {ngrok_tunnel.public_url}")
        except Exception as e:
            logger.error(f"Failed to start ngrok: {e}")
            print(f"{colorama.Fore.RED}Failed to start ngrok. Remote access will not be available.{colorama.Style.RESET_ALL}")
            tunnel_active = False

    # Print the startup banner
    print_startup_banner()
    
    # Start the Flask server
    try:
        app.run(host="0.0.0.0", port=3001)
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        print(f"{colorama.Fore.RED}An error occurred: {e}{colorama.Style.RESET_ALL}")
        input("Press Enter to exit.")