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
import threading

from optimisewait import set_autopath, set_altpath
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
from modules.project_utils import get_ui_projects_data, get_ui_active_windows, get_project_icon_info
from modules.window_manager import focus_and_maximize_window, wait_for_vscode_window

# --- Newly Extracted Modules ---
from modules.chat_manager import add_chat_message, chat_history
from modules.llm_utils import get_content_text
from modules.automation_utils import process_optimisewait_message
from modules.project_manager import (load_project_links, save_project_links, 
                                     filter_ignored_projects, get_all_projects_with_ignore_state)

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

# --- System Busy State ---
system_busy = False

# --- Task Queue State ---
task_queue = []
current_queue_task = None
queue_lock = threading.Lock()

def process_next_queue_item():
    global task_queue, current_queue_task, global_completion_status, global_last_reply, system_busy
    
    while True:
        # Wait if the system is currently processing any LLM interaction
        while system_busy:
            time.sleep(2)
            
        with queue_lock:
            # Re-check inside lock to ensure another thread didn't beat us
            if system_busy:
                continue
                
            if not task_queue:
                current_queue_task = None
                return
                
            current_queue_task = task_queue.pop(0)
            system_busy = True
            break # Got the task, exit the polling loop
    
    try:
        project_path = current_queue_task.get('project_path')
        message = current_queue_task.get('message')
        
        vscode_exe = find_vscode_executable()
        if vscode_exe and project_path and os.path.isdir(project_path):
            subprocess.Popen([vscode_exe, project_path], creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            project_name = os.path.basename(project_path)
            wait_for_vscode_window(project_name)
        
        time.sleep(1) # Extra stability wait
        
        global_completion_status = False
        global_last_reply = ""
        add_chat_message('user', message)
        process_optimisewait_message(message, debug=(terminal_log_level == 'debug'))
    except Exception as e:
        logger.error(f"Error processing queue item: {e}")
        system_busy = False
        current_queue_task = None
        threading.Thread(target=process_next_queue_item, daemon=True).start()

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

# --- CORE LOGIC ---
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
    return talkto(current_model, full_prompt, image_list, debug=debug_mode,humanize=True, windmouse=True)

# --- FLASK ROUTES ---
@app.route('/', methods=['GET'])
@limiter.exempt
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
@limiter.exempt
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
@limiter.exempt
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
@limiter.exempt
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
@limiter.exempt
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
@limiter.exempt
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
@limiter.exempt
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
@limiter.exempt
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
    global system_busy
    system_busy = True
    try:
        clear_previous_alert(alert_state)
        
        data = request.get_json()
        if not data or 'messages' not in data:
            return jsonify({'error': {'message': 'Invalid request format'}}), 400

        prompt = get_content_text(data['messages'][-1].get('content', ''), debug=(terminal_log_level == 'debug'))
        
        is_streaming = data.get('stream', False)
        response = handle_llm_interaction(prompt)
        request_id = f'chatcmpl-{int(time.time())}'

        has_completion = "<attempt_completion>" in response
        
        summary_match = re.search(r"<summary>(.*?)</summary>", response, re.DOTALL)
        summary = summary_match.group(1).strip() if summary_match else None

        added_to_chat = False
        def chat_adder_with_full_text(r, t):
            nonlocal added_to_chat
            add_chat_message(r, t, full_text=response)
            added_to_chat = True

        global global_completion_status, global_last_reply
        if has_completion:
            system_busy = False
            global_completion_status = True
            global_last_reply = summary if summary else "Task completed successfully."
            if terminal_alert_level in ['completions', 'all']:
                print_completion_alert(alert_state)
            
            # TRIGGER QUEUE NEXT ITEM
            threading.Thread(target=process_next_queue_item, daemon=True).start()
            
        elif summary:
            global_last_reply = summary
            if terminal_alert_level == 'all':
                print_summary_alert(summary, chat_adder_with_full_text)

        ntfy_topic = config.get('ntfy_topic', '')
        if ntfy_notification_level == 'all':
            if has_completion:
                send_ntfy_notification(
                    topic=ntfy_topic,
                    simple_title="Cline-X: Task Completion",
                    full_content=summary or "Task completion submitted.",
                    add_chat_message_func=chat_adder_with_full_text,
                    tags="tada"
                )
            elif summary:
                send_ntfy_notification(
                    topic=ntfy_topic,
                    simple_title="[INFO] Cline-X: AI Response",
                    full_content=summary,
                    add_chat_message_func=chat_adder_with_full_text,
                    tags="robot_face"
                )
        elif ntfy_notification_level == 'completion' and has_completion:
            send_ntfy_notification(
                topic=ntfy_topic,
                simple_title="Cline-X: Task Completion",
                full_content=response,
                add_chat_message_func=chat_adder_with_full_text,
                tags="tada"
            )

        if not added_to_chat:
            chat_adder_with_full_text('assistant', summary if summary else ("Task completed successfully." if has_completion else "Processed response."))
        
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
@limiter.exempt
def dashboard():
    all_projects = get_all_projects_with_ignore_state()
    links = load_project_links()
    for p in all_projects:
        p_path = p.get('path')
        if p_path:
            norm_path = os.path.normcase(os.path.normpath(p_path))
            p['dev_link'] = links.get(norm_path, "")
            
    projects_data = [p for p in all_projects if not p.get('is_ignored')]
    
    active_windows = filter_ignored_projects(get_ui_active_windows())
    for win in active_windows:
        p_path = win.get('path')
        if p_path:
            norm_path = os.path.normcase(os.path.normpath(p_path))
            win['dev_link'] = links.get(norm_path, "")
        else:
            win['dev_link'] = ""
            
    return render_template('dashboard.html', projects=projects_data, active_windows=active_windows, all_projects=all_projects)

@app.route('/cline_quest')
@limiter.exempt
def cline_quest():
    return render_template('cline_quest.html')

@app.route('/multi_project')
@limiter.exempt
def multi_project():
    all_projects = get_all_projects_with_ignore_state()
    links = load_project_links()
    for p in all_projects:
        p_path = p.get('path')
        if p_path:
            norm_path = os.path.normcase(os.path.normpath(p_path))
            p['dev_link'] = links.get(norm_path, "")
            
    projects_data = [p for p in all_projects if not p.get('is_ignored')]
    return render_template('multi_project.html', projects=projects_data, all_projects=all_projects)

@app.route('/api/batch_status')
@limiter.exempt
def batch_status():
    return jsonify({
        'completed': global_completion_status,
        'last_reply': global_last_reply
    })

@app.route('/chat')
@limiter.exempt
def chat():
    project_name = request.args.get('project', 'Project')
    project_path, project_has_icon = get_project_icon_info(project_name)
    return render_template('chat.html', project_name=project_name, project_path=project_path, project_has_icon=project_has_icon)

@app.route('/api/active')
@limiter.exempt
def api_active():
    active = filter_ignored_projects(get_ui_active_windows())
    links = load_project_links()
    for win in active:
        p_path = win.get('path')
        if p_path:
            norm_path = os.path.normcase(os.path.normpath(p_path))
            win['dev_link'] = links.get(norm_path, "")
        else:
            win['dev_link'] = ""
    return jsonify(active)

@app.route('/api/project_link', methods=['POST'])
@limiter.exempt
def update_project_link():
    try:
        data = request.get_json()
        path = data.get('path')
        link = data.get('link')
        
        if not path:
            return jsonify({'status': 'error', 'message': 'Invalid path'}), 400
            
        links = load_project_links()
        norm_path = os.path.normcase(os.path.normpath(path))
        
        if link:
            links[norm_path] = link
        else:
            if norm_path in links:
                del links[norm_path]
                
        save_project_links(links)
        return jsonify({'status': 'success', 'message': 'Project link updated'})
    except Exception as e:
        logger.error(f"Error updating project link: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/screenshot')
@limiter.exempt
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
@limiter.exempt
def get_icon():
    project_path = request.args.get('path')
    if not project_path:
        return abort(404)
    
    if '?' in project_path:
        project_path = project_path.split('?')[0]
        
    icon_path = find_project_icon(project_path)
    if icon_path and os.path.exists(icon_path):
        return send_file(icon_path, mimetype='image/x-icon')
    return abort(404)

@app.route('/launch', methods=['POST'])
@limiter.exempt
def launch():
    project_path = request.json.get('path')
    vscode_exe = find_vscode_executable()
    
    if vscode_exe and project_path and os.path.isdir(project_path):
        try:
            subprocess.Popen([vscode_exe, project_path], creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            project_name = os.path.basename(project_path)
            wait_for_vscode_window(project_name)
            return jsonify({'status': 'success', 'message': 'Opening...', 'project_name': project_name})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
    return jsonify({'status': 'error', 'message': 'Invalid path'}), 400

@app.route('/focus', methods=['POST'])
@limiter.exempt
def focus():
    title_to_find = request.json.get('title')
    project_name = focus_and_maximize_window(title_to_find)
    if project_name:
        return jsonify({'status': 'success', 'message': 'Focused', 'project_name': project_name})
    return jsonify({'status': 'error', 'message': 'Window not found'}), 404

@app.route('/send_message', methods=['POST'])
@limiter.limit("20 per minute")
def send_message():
    global global_completion_status, global_last_reply, system_busy
    data = request.json
    message = data.get('message')
    
    if not message:
        return jsonify({'status': 'error', 'message': 'Message cannot be empty'}), 400

    try:
        system_busy = True
        global_completion_status = False
        global_last_reply = ""
        add_chat_message('user', message)
        process_optimisewait_message(message, debug=(terminal_log_level == 'debug'))
        return jsonify({'status': 'success', 'message': 'Message processed'})
    except Exception as e:
        logger.error(f"Message processing failed: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/ignore', methods=['POST'])
@limiter.exempt
def ignore_project():
    project_path = request.json.get('path')
    if project_path:
        save_ignored_folder(project_path)
        return jsonify({'status': 'success', 'message': 'Project ignored'})
    return jsonify({'status': 'error', 'message': 'Invalid path'}), 400

@app.route('/api/ignored', methods=['GET'])
@limiter.exempt
def get_ignored_route():
    return jsonify(load_ignored_folders())

@app.route('/api/unignore', methods=['POST'])
@limiter.exempt
def unignore_project_route():
    project_path = request.json.get('path')
    if not project_path:
        return jsonify({'status': 'error', 'message': 'Invalid path'}), 400
    
    ignored = load_ignored_folders()
    norm_target = os.path.normcase(os.path.normpath(project_path))
    new_ignored = [p for p in ignored if os.path.normcase(os.path.normpath(p)) != norm_target]
    
    try:
        ignored_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ignored_folders.json')
        with open(ignored_file_path, 'w', encoding='utf-8') as f:
            json.dump(new_ignored, f, indent=4)
        return jsonify({'status': 'success', 'message': 'Project unignored'})
    except Exception as e:
        logger.error(f"Failed to unignore project: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/multi_project_state', methods=['GET', 'POST'])
@limiter.exempt
def multi_project_state_route():
    state_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'multi_project_state.json')
    if request.method == 'GET':
        try:
            if os.path.exists(state_file_path):
                with open(state_file_path, 'r', encoding='utf-8') as f:
                    return jsonify(json.load(f))
            return jsonify([])
        except Exception as e:
            logger.error(f"Error reading multi_project_state: {e}")
            return jsonify([])
    
    if request.method == 'POST':
        try:
            state_data = request.get_json()
            with open(state_file_path, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=4)
            return jsonify({'status': 'success'})
        except Exception as e:
            logger.error(f"Error saving multi_project_state: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_messages')
@limiter.exempt
def get_messages():
    return jsonify(chat_history)

@app.route('/restart', methods=['GET'])
@limiter.exempt
def restart_server():
    try:
        logger.info("Restart command received. Spawning new window and exiting...")
        
        def perform_restart():
            # Allow a short delay for the HTTP response to be sent to the browser
            time.sleep(0.5)
            
            script_path = os.path.abspath(sys.argv[0])
            
            if os.name == 'nt':
                # Wait 2 seconds before starting the new process to ensure port is freed
                # Use CREATE_NEW_CONSOLE to pop open a new window
                command = f'timeout /t 2 /nobreak >nul & "{sys.executable}" "{script_path}"'
                subprocess.Popen(command, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                command = f'sleep 2 && "{sys.executable}" "{script_path}"'
                subprocess.Popen(command, shell=True)
            
            # Terminate the current application
            os._exit(0)

        threading.Thread(target=perform_restart, daemon=True).start()
        
        # Return a friendly self-refreshing page
        return """
        <html>
            <body style='background:#111;color:#eee;font-family:sans-serif;'>
                <h2 style='text-align:center;margin-top:20%;'>Restarting...</h2>
                <p style='text-align:center;color:#888;'>Opening a new window and terminating the current session.</p>
                <p style='text-align:center;color:#555;'>This page will auto-refresh in 5 seconds.</p>
                <script>
                    setTimeout(() => window.location.href='/', 5000);
                </script>
            </body>
        </html>
        """
    except Exception as e:
        logger.error(f"Restart failed: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/gui')
@limiter.exempt
def launch_gui_route():
    try:
        gui_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gui_app.py')
        subprocess.Popen([sys.executable, gui_script_path], creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        return "<html><body style='background:#111;color:#eee;font-family:sans-serif;'><h2 style='text-align:center;margin-top:20%;'>GUI Launched!</h2><p style='text-align:center;'>You can close this tab and return to the desktop application.</p><script>setTimeout(()=>window.close(),3000);</script></body></html>"
    except Exception as e:
        return str(e), 500

@app.route('/api/projects_list')
@limiter.exempt
def api_projects_list():
    projects = get_ui_projects_data()
    return jsonify(projects)

@app.route('/api/queue', methods=['GET', 'POST'])
@limiter.exempt
@csrf.exempt
def api_queue():
    global task_queue, current_queue_task, system_busy
    if request.method == 'GET':
        return jsonify({'queue': task_queue, 'current': current_queue_task, 'system_busy': system_busy})
    elif request.method == 'POST':
        data = request.json
        task = {
            'id': secrets.token_hex(8),
            'project_path': data.get('project_path'),
            'project_name': data.get('project_name'),
            'message': data.get('message')
        }
        with queue_lock:
            task_queue.append(task)
            
        if current_queue_task is None:
            threading.Thread(target=process_next_queue_item, daemon=True).start()
            
        return jsonify({'status': 'success', 'task': task})

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