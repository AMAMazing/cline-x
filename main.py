from flask import Flask, jsonify, request, Response, abort, render_template, send_file
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import time
from time import sleep
import os
import logging
import json
import io
import re
import secrets
from functools import wraps
from pyngrok import ngrok
import sys
from dotenv import load_dotenv, set_key
import colorama
import subprocess
from datetime import timedelta
import pyautogui

from optimisewait import optimiseWait, set_autopath, set_altpath
from talktollm import talkto
from typing import Union, List, Dict

# --- Import Local Modules ---
from modules.config_utils import get_app_path, read_config, write_config, get_rules_content, APP_PATH, DOTENV_PATH
from modules.clipboard_utils import set_clipboard, set_clipboard_image
from modules.vscode_utils import (force_bring_to_front, load_ignored_folders, save_ignored_folder,
                                  find_vscode_executable, get_vscode_projects, find_project_icon,
                                  get_active_windows, gw)
from modules.terminal_utils import clear_previous_alert, print_completion_alert, print_summary_alert, print_startup_banner
from modules.notify_utils import send_ntfy_notification

# Fix for Windows Unicode Output
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

load_dotenv(dotenv_path=DOTENV_PATH)

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
    def format(self, record):
        if terminal_log_level == 'none':
            return ''
        elif terminal_log_level == 'minimal':
            if 'Starting' in record.msg or 'notification' in record.msg.lower():
                if 'Starting' in record.msg:
                    return f"Starting {current_model.upper()} interaction"
                elif 'Successfully sent' in record.msg:
                    return "Sent notification"
                return ''
            return ''
        elif terminal_log_level == 'debug':
            return super().format(record)
        else:
            if record.levelno >= logging.INFO:
                return super().format(record)
            return ''

handler = logging.StreamHandler()
handler.setFormatter(CustomFormatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG if terminal_log_level == 'debug' else logging.INFO)

# --- State for clearing the alert ---
alert_state = {'lines_printed': 0, 'active': False}

# --- Batch Process State ---
global_completion_status = False
global_last_reply = ""

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
        current_auth_required = str(config.get('auth_required', 'False')).lower() == 'true'
        if not current_auth_required:
            return func(*args, **kwargs)
            
        if request.headers.get('X-API-Key') == API_KEY or request.headers.get('Authorization', '').replace('Bearer ', '') == API_KEY:
            return func(*args, **kwargs)
            
        if request.args.get('api_key') == API_KEY:
             return func(*args, **kwargs)
             
        abort(401, description="Invalid or missing API key")
    return wrapper

app = Flask(__name__)
app.secret_key = os.urandom(24) 
app.permanent_session_lifetime = timedelta(days=30) 
csrf = CSRFProtect(app) 

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

def process_optimisewait_message(message):
    optimiseWait('newchat', autopath='linkimages')
    optimiseWait('taskhere', autopath='linkimages')
    
    set_clipboard(message, debug=(terminal_log_level == 'debug'))
    time.sleep(0.1)
    
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.1) 
    pyautogui.press('enter')

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
                    set_clipboard_image(image_data, debug=(terminal_log_level == 'debug'))
                parts.append(f"[Image: An uploaded image]")
        return "\n".join(parts)
    return ""

def handle_llm_interaction(prompt):
    global last_request_time
    clear_previous_alert(alert_state)
    
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

    current_time_str = time.strftime('%Y-%m-%d %H:%M:%S')
    headers_log = f"{current_time_str} - INFO - Request data: {json.dumps(request_json)}"

    unified_rules = get_rules_content()
    prompt_instructions = [headers_log]

    if terminal_alert_level == 'all' or ntfy_notification_level == 'all':
        summary_instruction = r"You MUST include a `<summary>` tag inside your `<thinking>` block for every tool call. This summary should be a very brief, user-friendly explanation of the action you are about to take. For example: `<summary>Reading the project's configuration to check dependencies.</summary>`."
        prompt_instructions.append(summary_instruction)

    prompt_instructions.append(prompt)
    prompt_instructions.append(unified_rules)
    
    fullpromptbefore = "\n".join(prompt_instructions)
    full_prompt = re.sub(r'data:image\/png;base64,[A-Za-z0-9+\/=]+', '', fullpromptbefore)

    debug_mode = (terminal_log_level == 'debug')
    return talkto(current_model, full_prompt, image_list, debug=debug_mode)

# --- FLASK ROUTES ---
@app.route('/', methods=['GET'])
def home():
    logger.debug(f"GET request to / from {request.remote_addr}")
    public_url = ngrok_tunnel.public_url if 'ngrok_tunnel' in globals() and ngrok_tunnel else 'Starting...'
    
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
            clear_previous_alert(alert_state)
            data = request.get_json()
            new_model = data['model'].lower()
            if new_model not in ['deepseek', 'gemini', 'aistudio', 'aistudio_flash', 'gemini-3.1-flash-lite-preview']:
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
        random_code = secrets.token_urlsafe(10)
        topic = f"clinex-{random_code}"
        
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
            ngrok_authtoken = os.getenv("NGROK_AUTHTOKEN")
            if not ngrok_authtoken:
                return jsonify({'success': False, 'error': 'NGROK_AUTHTOKEN not found in .env'}), 400
            
            try:
                ngrok.set_auth_token(ngrok_authtoken)
                ngrok_domain = os.getenv("NGROK_DOMAIN")
                if ngrok_domain:
                    ngrok_tunnel = ngrok.connect(3001, domain=ngrok_domain)
                else:
                    ngrok_tunnel = ngrok.connect(3001)

                tunnel_active = True
                logger.info(f"ngrok tunnel established: {ngrok_tunnel.public_url}")
                
                ntfy_topic = config.get('ntfy_topic', '')
                if ntfy_topic:
                    public_url = ngrok_tunnel.public_url
                    current_auth = str(config.get('auth_required', 'False')).lower() == 'true'
                    if current_auth:
                        public_url += f"/?api_key={API_KEY}"
                        
                    send_ntfy_notification(
                        topic=ntfy_topic,
                        simple_title="Cline-X: Remote Tunnel Active",
                        full_content=f"Your remote access tunnel is ready: {public_url}",
                        add_chat_message_func=add_chat_message,
                        tags="rocket"
                    )

            except Exception as e:
                logger.error(f"Failed to start ngrok: {e}")
                return jsonify({'success': False, 'error': f'Failed to start ngrok: {str(e)}'}), 500
                
        elif not new_state and tunnel_active:
            try:
                if 'ngrok_tunnel' in globals() and ngrok_tunnel:
                    ngrok.disconnect(ngrok_tunnel.public_url)
                tunnel_active = False
                logger.info("ngrok tunnel disconnected")
            except Exception as e:
                logger.error(f"Failed to stop ngrok: {e}")
                tunnel_active = False
        
        config['tunnel_active'] = str(tunnel_active)
        write_config(config)
        
        response_data = {'success': True, 'enabled': tunnel_active}
        if tunnel_active and 'ngrok_tunnel' in globals() and ngrok_tunnel:
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
            ntfy_topic = config.get('ntfy_topic', '')
            if ntfy_topic:
                send_ntfy_notification(
                    topic=ntfy_topic,
                    simple_title="Cline-X: Auth Enabled",
                    full_content=f"Security enabled. Your API Key is: {API_KEY}",
                    add_chat_message_func=add_chat_message,
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
        if new_theme not in ['light', 'dark'] or not new_theme:
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
    try:
        data = request.json
        path = data.get('path')
        
        if not path or not os.path.exists(path):
            return jsonify({'success': False, 'error': 'Path does not exist'}), 404
        
        os.startfile(path)
        return jsonify({'success': True, 'message': f'Opened {path}'})
    except Exception as e:
        logger.error(f"Failed to open path: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/chat/completions', methods=['POST'])
@require_api_key
@csrf.exempt
@limiter.limit("20 per minute")
def chat_completions():
    try:
        clear_previous_alert(alert_state)
        
        data = request.get_json()
        if not data or 'messages' not in data:
            return jsonify({'error': {'message': 'Invalid request format'}}), 400

        prompt = get_content_text(data['messages'][-1].get('content', ''))
        
        is_streaming = data.get('stream', False)
        response = handle_llm_interaction(prompt)
        request_id = f'chatcmpl-{int(time.time())}'

        has_completion = "<attempt_completion>" in response
        
        summary_match = re.search(r"<summary>(.*?)</summary>", response, re.DOTALL)
        summary = summary_match.group(1).strip() if summary_match else None

        global global_completion_status, global_last_reply
        if has_completion:
            global_completion_status = True
            global_last_reply = summary if summary else "Task completed successfully."
            if terminal_alert_level in ['completions', 'all']:
                print_completion_alert(alert_state)
        elif summary:
            global_last_reply = summary
            if terminal_alert_level == 'all':
                print_summary_alert(summary, add_chat_message)

        ntfy_topic = config.get('ntfy_topic', '')
        if ntfy_notification_level == 'all':
            if has_completion:
                send_ntfy_notification(
                    topic=ntfy_topic,
                    simple_title="Cline-X: Task Completion",
                    full_content=summary or "Task completion submitted.",
                    add_chat_message_func=add_chat_message,
                    tags="tada"
                )
            elif summary:
                send_ntfy_notification(
                    topic=ntfy_topic,
                    simple_title="[INFO] Cline-X: AI Response",
                    full_content=summary,
                    add_chat_message_func=add_chat_message,
                    tags="robot_face"
                )
        elif ntfy_notification_level == 'completion' and has_completion:
            send_ntfy_notification(
                topic=ntfy_topic,
                simple_title="Cline-X: Task Completion",
                full_content=response,
                add_chat_message_func=add_chat_message,
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

@app.route('/dashboard')
def dashboard():
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

@app.route('/multi_project')
def multi_project():
    all_projects = get_vscode_projects()
    ignored_folders = load_ignored_folders()
    visible_projects = [p for p in all_projects if p not in ignored_folders]
    
    projects_data = []
    for p in visible_projects:
        projects_data.append({
            'path': p,
            'name': os.path.basename(p),
            'has_icon': find_project_icon(p) is not None
        })
    return render_template('multi_project.html', projects=projects_data)

@app.route('/api/batch_status')
def batch_status():
    return jsonify({
        'completed': global_completion_status,
        'last_reply': global_last_reply
    })

@app.route('/chat')
def chat():
    project_name = request.args.get('project', 'Project')
    
    all_projects = get_vscode_projects()
    project_path = ""
    project_has_icon = False
    
    matched_proj = next((p for p in all_projects if os.path.basename(p) == project_name), None)
    if matched_proj:
        project_path = matched_proj
        if find_project_icon(matched_proj):
            project_has_icon = True
            
    return render_template('chat.html', project_name=project_name, project_path=project_path, project_has_icon=project_has_icon)

@app.route('/api/active')
def api_active():
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
    project_path = request.args.get('path')
    if not project_path:
        return abort(404)
    
    # Strip any cache-busting parameters if they accidentally got into the path
    if '?' in project_path:
        project_path = project_path.split('?')[0]
        
    icon_path = find_project_icon(project_path)
    if icon_path and os.path.exists(icon_path):
        return send_file(icon_path, mimetype='image/x-icon')
    return abort(404)

@app.route('/launch', methods=['POST'])
def launch():
    project_path = request.json.get('path')
    vscode_exe = find_vscode_executable()
    
    if vscode_exe and project_path and os.path.isdir(project_path):
        try:
            subprocess.Popen([vscode_exe, project_path], creationflags=subprocess.CREATE_NO_WINDOW)
            project_name = os.path.basename(project_path)
            
            found_window = False
            for i in range(100): 
                time.sleep(0.1) 
                if gw:
                    windows = gw.getWindowsWithTitle(project_name)
                    for win in windows:
                        if "Visual Studio Code" in win.title:
                            try:
                                force_bring_to_front(win._hWnd)
                                found_window = True
                            except Exception as e:
                                logger.error(f"Error focusing new window: {e}")
                            break
                if found_window:
                    break
            
            if optimiseWait:
                try:
                    optimiseWait('maximize', autopath='linkimages')
                except Exception as e:
                    logger.error(f"OptimiseWait maximize failed: {e}")

            return jsonify({'status': 'success', 'message': 'Opening...', 'project_name': project_name})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
    return jsonify({'status': 'error', 'message': 'Invalid path'}), 400

@app.route('/focus', methods=['POST'])
def focus():
    title_to_find = request.json.get('title')
    try:
        if gw:
            windows = gw.getWindowsWithTitle(title_to_find)
            if windows:
                win = windows[0]
                # Improved project name extraction: VS Code title is typically "filename - projectname - Visual Studio Code"
                # We want only the "projectname" part.
                raw_title = win.title.replace(" - Visual Studio Code", "").strip()
                if " - " in raw_title:
                    parts = raw_title.split(" - ")
                    # If it's "file - project", we take the last part.
                    project_name = parts[-1].strip()
                else:
                    project_name = raw_title

                force_bring_to_front(win._hWnd)
                
                if optimiseWait:
                    try:
                        optimiseWait('maximize', autopath='linkimages')
                    except Exception as e:
                        logger.error(f"OptimiseWait maximize failed: {e}")
                
                return jsonify({'status': 'success', 'message': 'Focused', 'project_name': project_name})
        
        return jsonify({'status': 'error', 'message': 'Window not found'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/send_message', methods=['POST'])
@limiter.limit("20 per minute")
def send_message():
    global global_completion_status, global_last_reply
    data = request.json
    message = data.get('message')
    
    if not message:
        return jsonify({'status': 'error', 'message': 'Message cannot be empty'}), 400

    try:
        global_completion_status = False
        global_last_reply = ""
        add_chat_message('user', message)
        process_optimisewait_message(message)
        return jsonify({'status': 'success', 'message': 'Message processed'})
    except Exception as e:
        logger.error(f"Message processing failed: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/ignore', methods=['POST'])
def ignore_project():
    project_path = request.json.get('path')
    if project_path:
        save_ignored_folder(project_path)
        return jsonify({'status': 'success', 'message': 'Project ignored'})
    return jsonify({'status': 'error', 'message': 'Invalid path'}), 400

@app.route('/get_messages')
def get_messages():
    return jsonify(chat_history)

ngrok_tunnel = None

if __name__ == '__main__':
    colorama.init(autoreset=True)

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

    print_startup_banner(
        current_model=current_model,
        current_theme=current_theme,
        terminal_log_level=terminal_log_level,
        terminal_alert_level=terminal_alert_level,
        ntfy_notification_level=ntfy_notification_level,
        tunnel_active=tunnel_active,
        auth_required=auth_required,
        ngrok_tunnel=ngrok_tunnel,
        API_KEY=API_KEY,
        APP_PATH=APP_PATH
    )
    
    try:
        app.run(host="0.0.0.0", port=3001)
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        print(f"{colorama.Fore.RED}An error occurred: {e}{colorama.Style.RESET_ALL}")
        input("Press Enter to exit.")