import os
import json
import time
import threading
import secrets
from datetime import date
from flask import Blueprint, jsonify, request, render_template, Response

from modules.pomodoro_manager import load_pomodoro_stats, pomodoro_state
import modules.queue_manager as queue_manager
from modules.config_utils import read_config

pomodoro_bp = Blueprint('pomodoro_bp', __name__)

ALLOWED_CORS_HEADERS = 'Content-Type, Authorization, x-api-key, X-API-Key, x-client, X-Client, *'

@pomodoro_bp.before_app_request
def handle_options_preflight():
    if request.method == 'OPTIONS':
        response = Response(status=200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = ALLOWED_CORS_HEADERS
        response.headers['Access-Control-Max-Age'] = '86400'
        return response

@pomodoro_bp.after_app_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = ALLOWED_CORS_HEADERS
    return response

@pomodoro_bp.route('/pomodoro')
def pomodoro():
    return render_template('pomodoro.html')

@pomodoro_bp.route('/api/pomodoro/state', methods=['GET'])
def pomodoro_get_state():
    return jsonify(pomodoro_state)

@pomodoro_bp.route('/api/pomodoro/start', methods=['POST'])
def pomodoro_start():
    data = request.json
    tasks = data.get('tasks', [])
    if not tasks:
        return jsonify({'status': 'error', 'message': 'No tasks provided'}), 400

    with queue_manager.queue_lock:
        for t in tasks:
            t['id'] = secrets.token_hex(8)
        pomodoro_state['queue'] = tasks
        pomodoro_state['is_break'] = True
        pomodoro_state['break_started_at'] = time.time()
        pomodoro_state['sprint_size'] = len(tasks)

    if not queue_manager.state['system_busy']:
        config = read_config()
        terminal_log_level = config.get('terminal_log_level', 'default')
        threading.Thread(target=queue_manager.process_next_queue_item, args=(terminal_log_level,), daemon=True).start()

    return jsonify({'status': 'success'})

@pomodoro_bp.route('/api/pomodoro/clear_completed', methods=['POST'])
def pomodoro_clear_completed():
    data = request.json
    task_id = data.get('id')
    pomodoro_state['completed'] = [t for t in pomodoro_state['completed'] if t.get('id') != task_id]
    return jsonify({'status': 'success'})

@pomodoro_bp.route('/api/pomodoro/stats', methods=['GET'])
def pomodoro_get_stats():
    stats = load_pomodoro_stats()
    today_str = date.today().isoformat()
    stats['today_count'] = stats.get('daily_counts', {}).get(today_str, 0)
    return jsonify(stats)

@pomodoro_bp.route('/api/pomodoro/presets', methods=['GET', 'POST'])
def pomodoro_presets():
    preset_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pomodoro_presets.json')
    if request.method == 'GET':
        if os.path.exists(preset_file):
            try:
                with open(preset_file, 'r', encoding='utf-8') as f:
                    return jsonify(json.load(f))
            except:
                return jsonify({})
        return jsonify({})
    elif request.method == 'POST':
        try:
            with open(preset_file, 'w', encoding='utf-8') as f:
                json.dump(request.json, f, indent=4)
            return jsonify({'status': 'success'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500