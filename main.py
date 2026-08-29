from flask import Flask, jsonify, request, Response, abort, render_template, send_file
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import time
from time import sleep
import os
import logging
import json
import re
import secrets
from functools import wraps
from pyngrok import ngrok
import sys
from dotenv import load_dotenv, set_key
import colorama
import subprocess
from datetime import timedelta, date
import threading
import socket
import atexit
import signal
import ctypes

from optimisewait import set_autopath, set_altpath
from talktollm import talkto
from typing import Union, List, Dict

# --- Import Local Modules ---
from modules.config_utils import get_app_path, read_config, write_config, get_rules_content, APP_PATH, DOTENV_PATH
from modules.terminal_utils import clear_previous_alert, print_completion_alert, print_summary_alert, print_startup_banner
from modules.notify_utils import send_ntfy_notification

# --- Extracted Modules ---
from modules.chat_manager import add_chat_message, chat_history, get_project_messages, current_active_project, current_active_session_id
from modules.llm_utils import get_content_text
from modules.automation_utils import process_optimisewait_message
from modules.pomodoro_manager import record_sprint_completion, pomodoro_state
import modules.queue_manager as queue_manager
from modules.auth_utils import require_api_key, API_KEY
from modules.project_routes import project_bp
from modules.pomodoro_routes import pomodoro_bp

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

# --- ROBUST SINGLE INSTANCE & PORT 3001 ENFORCEMENT ---
LOCK_FILE_PATH = os.path.join(APP_PATH, '.cline_x.lock')
_named_mutex_handle = None

def is_pid_alive(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    if os.name == 'nt':
        try:
            cmd = f'tasklist /FI "PID eq {pid}" /FO CSV /NH'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
            return f'"{pid}"' in output or str(pid) in output
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

def terminate_pid_tree(pid: int):
    if pid <= 0 or pid == os.getpid():
        return
    try:
        if os.name == 'nt':
            subprocess.run(f'taskkill /F /T /PID {pid}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, signal.SIGKILL)
    except Exception:
        pass

def get_listening_pids_on_port(port: int) -> List[int]:
    pids = []
    if os.name == 'nt':
        try:
            output = subprocess.check_output('netstat -ano -p tcp', shell=True, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
            for line in output.splitlines():
                line = line.strip()
                if not line:
                    continue
                match = re.search(rf':{port}\s+.*(?:LISTENING|ESTABLISHED)\s+(\d+)', line, re.IGNORECASE)
                if match:
                    found_pid = int(match.group(1))
                    if found_pid > 0 and found_pid != os.getpid() and found_pid not in pids:
                        pids.append(found_pid)
        except Exception:
            pass
    return pids

def is_port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(('127.0.0.1', port)) == 0

def wait_for_port_freed(port: int, max_wait_sec: float = 4.0) -> bool:
    start = time.time()
    while time.time() - start < max_wait_sec:
        if not is_port_listening(port):
            return True
        time.sleep(0.2)
    return not is_port_listening(port)

def cleanup_lock_and_mutex():
    global _named_mutex_handle
    try:
        if os.path.exists(LOCK_FILE_PATH):
            with open(LOCK_FILE_PATH, 'r') as f:
                content = f.read().strip()
            if content == str(os.getpid()):
                os.remove(LOCK_FILE_PATH)
    except Exception:
        pass

    if _named_mutex_handle and os.name == 'nt':
        try:
            ctypes.windll.kernel32.CloseHandle(_named_mutex_handle)
            _named_mutex_handle = None
        except Exception:
            pass

def enforce_single_instance(port: int = 3001):
    global _named_mutex_handle

    if os.path.exists(LOCK_FILE_PATH):
        try:
            with open(LOCK_FILE_PATH, 'r') as f:
                old_pid_str = f.read().strip()
            if old_pid_str.isdigit():
                old_pid = int(old_pid_str)
                if old_pid != os.getpid() and is_pid_alive(old_pid):
                    print(f"{colorama.Fore.YELLOW}[Single-Instance] Terminating previous background instance (PID: {old_pid})...{colorama.Style.RESET_ALL}")
                    terminate_pid_tree(old_pid)
                    time.sleep(0.5)
        except Exception:
            pass

    occupying_pids = get_listening_pids_on_port(port)
    for p in occupying_pids:
        print(f"{colorama.Fore.YELLOW}[Single-Instance] Port {port} is occupied by PID {p}. Freeing port...{colorama.Style.RESET_ALL}")
        terminate_pid_tree(p)

    if not wait_for_port_freed(port, max_wait_sec=3.0):
        for p in get_listening_pids_on_port(port):
            terminate_pid_tree(p)
        wait_for_port_freed(port, max_wait_sec=2.0)

    if os.name == 'nt':
        try:
            mutex_name = "Local\\ClineX_FlaskServer_SingleInstance_3001"
            _named_mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
        except Exception:
            pass

    try:
        with open(LOCK_FILE_PATH, 'w') as f:
            f.write(str(os.getpid()))
        atexit.register(cleanup_lock_and_mutex)
    except Exception:
        pass

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

alert_state = {'lines_printed': 0, 'active': False}

app = Flask(__name__)
app.secret_key = os.urandom(24) 
app.permanent_session_lifetime = timedelta(days=30) 
csrf = CSRFProtect(app) 

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

app.register_blueprint(project_bp)
app.register_blueprint(pomodoro_bp)

limiter.exempt(project_bp)
limiter.exempt(pomodoro_bp)
csrf.exempt(pomodoro_bp)

last_request_time = 0
MIN_REQUEST_INTERVAL = 5

set_autopath(r"D:\cline-x-claudeweb\images")
set_altpath(r"D:\cline-x-claudeweb\images\alt1440")

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
    return talkto(current_model, full_prompt, image_list, debug=debug_mode, humanize=True, windmouse=True)

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
                           queue_timeout_minutes=int(config.get('queue_timeout_minutes', 5)),
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
    queue_manager.state['system_busy'] = True
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

        if has_completion:
            queue_manager.state['system_busy'] = False
            queue_manager.state['global_completion_status'] = True
            queue_manager.state['global_last_reply'] = summary if summary else "Task completed successfully."
            if terminal_alert_level in ['completions', 'all']:
                print_completion_alert(alert_state)
            
            if queue_manager.state['current_queue_task'] and queue_manager.state['current_queue_task'].get('is_pomodoro'):
                queue_manager.state['current_queue_task']['result'] = queue_manager.state['global_last_reply']
                pomodoro_state['completed'].append(queue_manager.state['current_queue_task'])
                pomodoro_state['current_task'] = None
                
                if not pomodoro_state['queue']:
                    pomodoro_state['is_break'] = False
                    record_sprint_completion(pomodoro_state.get('sprint_size', 0))
                    pomodoro_state['break_started_at'] = None
                    pomodoro_state['sprint_size'] = 0
                    ntfy_topic = config.get('ntfy_topic', '')
                    if ntfy_topic:
                        send_ntfy_notification(
                            topic=ntfy_topic,
                            simple_title="Break Ended!",
                            full_content="All Sprint tasks are completed. Time to review!",
                            add_chat_message_func=chat_adder_with_full_text,
                            tags="tomato"
                        )
            
            threading.Thread(target=queue_manager.process_next_queue_item, args=(terminal_log_level,), daemon=True).start()
            
        elif summary:
            queue_manager.state['global_last_reply'] = summary
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

@app.route('/api/batch_status')
@limiter.exempt
def batch_status():
    return jsonify({
        'completed': queue_manager.state['global_completion_status'],
        'last_reply': queue_manager.state['global_last_reply'],
        'system_busy': queue_manager.state['system_busy']
    })

@app.route('/send_message', methods=['POST'])
@limiter.limit("20 per minute")
def send_message():
    data = request.json
    message = data.get('message')
    project_name = data.get('project_name') or current_active_project
    
    if not message:
        return jsonify({'status': 'error', 'message': 'Message cannot be empty'}), 400

    try:
        queue_manager.state['system_busy'] = True
        queue_manager.state['global_completion_status'] = False
        queue_manager.state['global_last_reply'] = ""
        add_chat_message('user', message, project_name=project_name)
        process_optimisewait_message(message, debug=(terminal_log_level == 'debug'))
        return jsonify({'status': 'success', 'message': 'Message processed'})
    except Exception as e:
        logger.error(f"Message processing failed: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_messages')
@limiter.exempt
def get_messages():
    project_name = request.args.get('project') or current_active_project or 'default'
    session_id = request.args.get('session') or current_active_session_id
    msgs = get_project_messages(project_name, session_id)
    if not msgs and chat_history:
        return jsonify(chat_history)
    return jsonify(msgs)

@app.route('/restart', methods=['GET'])
@limiter.exempt
def restart_server():
    try:
        logger.info("Restart command received. Spawning new window and exiting...")
        
        def perform_restart():
            time.sleep(0.5)
            script_path = os.path.abspath(sys.argv[0])
            
            if os.name == 'nt':
                command = f'timeout /t 2 /nobreak >nul & "{sys.executable}" "{script_path}"'
                subprocess.Popen(command, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                command = f'sleep 2 && "{sys.executable}" "{script_path}"'
                subprocess.Popen(command, shell=True)
            
            os._exit(0)

        threading.Thread(target=perform_restart, daemon=True).start()
        
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

@app.route('/api/queue', methods=['GET', 'POST'])
@limiter.exempt
@csrf.exempt
def api_queue():
    if request.method == 'GET':
        return jsonify({'queue': queue_manager.task_queue, 'current': queue_manager.state['current_queue_task'], 'system_busy': queue_manager.state['system_busy']})
    elif request.method == 'POST':
        data = request.json
        proj_name = data.get('project_name') or current_active_project
        msg_text = data.get('message')
        
        task = {
            'id': secrets.token_hex(8),
            'project_path': data.get('project_path'),
            'project_name': proj_name,
            'message': msg_text
        }
        
        if msg_text:
            add_chat_message('user', msg_text, project_name=proj_name)
            
        with queue_manager.queue_lock:
            queue_manager.task_queue.append(task)
            
        if queue_manager.state['current_queue_task'] is None:
            threading.Thread(target=queue_manager.process_next_queue_item, args=(terminal_log_level,), daemon=True).start()
            
        return jsonify({'status': 'success', 'task': task})

@app.route('/api/timeout', methods=['POST'])
@limiter.exempt
def set_timeout():
    global config
    try:
        data = request.get_json()
        timeout = int(data.get('timeout', 5))
        config['queue_timeout_minutes'] = str(timeout)
        write_config(config)
        logger.info(f"Queue wait timeout set to: {timeout} minutes")
        return jsonify({'success': True, 'timeout': timeout})
    except Exception as e:
        logger.error(f"Error setting timeout: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

ngrok_tunnel = None

if __name__ == '__main__':
    colorama.init(autoreset=True)

    enforce_single_instance(port=3001)

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