import os
import io
import json
import logging
import subprocess
import sys
import pyautogui
from flask import Blueprint, jsonify, request, render_template, send_file, abort

from modules.project_manager import (load_project_links, save_project_links, 
                                     filter_ignored_projects, get_all_projects_with_ignore_state)
from modules.vscode_utils import find_vscode_executable, save_ignored_folder, load_ignored_folders, find_project_icon
from modules.project_utils import get_ui_projects_data, get_ui_active_windows, get_project_icon_info
from modules.window_manager import focus_and_maximize_window, wait_for_vscode_window

logger = logging.getLogger(__name__)
project_bp = Blueprint('project_bp', __name__)

@project_bp.route('/dashboard')
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

@project_bp.route('/cline_quest')
def cline_quest():
    all_projects = get_all_projects_with_ignore_state()
    active_windows = filter_ignored_projects(get_ui_active_windows())
    links = load_project_links()
    
    pinned_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pinned_quests.json')
    pinned_data = {}
    if os.path.exists(pinned_file):
        try:
            with open(pinned_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    pinned_data = {path: {"function": 0, "money": 0, "users": 0} for path in data}
                elif isinstance(data, dict):
                    pinned_data = data
        except:
            pass
            
    pinned_paths = list(pinned_data.keys())
    active_paths = [os.path.normcase(os.path.normpath(w.get('path'))) for w in active_windows if w.get('path')]
    
    pinned_inactive_projects = []
    unpinned_inactive_projects = []
    
    for p in all_projects:
        if p.get('is_ignored'):
            continue
        p_path = p.get('path')
        if not p_path:
            continue
            
        norm = os.path.normcase(os.path.normpath(p_path))
        p['dev_link'] = links.get(norm, "")
        p['is_pinned'] = norm in pinned_paths
        p['progress'] = pinned_data.get(norm, {"function": 0, "money": 0, "users": 0})
        
        if norm not in active_paths:
            if norm in pinned_paths:
                pinned_inactive_projects.append(p)
            else:
                unpinned_inactive_projects.append(p)
                
    active_quests = []
    
    for win in active_windows:
        p_path = win.get('path')
        if p_path:
            norm = os.path.normcase(os.path.normpath(p_path))
            win['dev_link'] = links.get(norm, "")
            win['is_pinned'] = norm in pinned_paths
            win['progress'] = pinned_data.get(norm, {"function": 0, "money": 0, "users": 0})
        else:
            win['dev_link'] = ""
            win['is_pinned'] = False
            win['progress'] = {"function": 0, "money": 0, "users": 0}
        win['is_active_window'] = True
        active_quests.append(win)
        
    for p in pinned_inactive_projects:
        p['is_active_window'] = False
        active_quests.append(p)
            
    return render_template('cline_quest.html', 
                           active_quests=active_quests, 
                           pinned_inactive_projects=pinned_inactive_projects,
                           unpinned_inactive_projects=unpinned_inactive_projects,
                           all_projects=all_projects)

@project_bp.route('/api/toggle_pin', methods=['POST'])
def toggle_pin():
    project_path = request.json.get('path')
    if not project_path:
        return jsonify({'status': 'error', 'message': 'Invalid path'}), 400
        
    pinned_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pinned_quests.json')
    pinned_data = {}
    if os.path.exists(pinned_file):
        try:
            with open(pinned_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    pinned_data = {path: {"function": 0, "money": 0, "users": 0} for path in data}
                elif isinstance(data, dict):
                    pinned_data = data
        except:
            pass
            
    norm_target = os.path.normcase(os.path.normpath(project_path))
    if norm_target in pinned_data:
        del pinned_data[norm_target]
        is_pinned = False
    else:
        pinned_data[norm_target] = {"function": 0, "money": 0, "users": 0}
        is_pinned = True
        
    try:
        with open(pinned_file, 'w', encoding='utf-8') as f:
            json.dump(pinned_data, f, indent=4)
        return jsonify({'status': 'success', 'is_pinned': is_pinned})
    except Exception as e:
        logger.error(f"Error saving pin state: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@project_bp.route('/api/update_progress', methods=['POST'])
def update_progress():
    try:
        data = request.get_json()
        project_path = data.get('path')
        if not project_path:
            return jsonify({'status': 'error', 'message': 'Invalid path'}), 400
            
        function_val = int(data.get('function', 0))
        money_val = int(data.get('money', 0))
        users_val = int(data.get('users', 0))
        
        pinned_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pinned_quests.json')
        pinned_data = {}
        if os.path.exists(pinned_file):
            try:
                with open(pinned_file, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    if isinstance(file_data, list):
                        pinned_data = {path: {"function": 0, "money": 0, "users": 0} for path in file_data}
                    elif isinstance(file_data, dict):
                        pinned_data = file_data
            except:
                pass
                
        norm_target = os.path.normcase(os.path.normpath(project_path))
        pinned_data[norm_target] = {
            "function": function_val,
            "money": money_val,
            "users": users_val
        }
        
        with open(pinned_file, 'w', encoding='utf-8') as f:
            json.dump(pinned_data, f, indent=4)
            
        return jsonify({'status': 'success', 'message': 'Progress updated'})
    except Exception as e:
        logger.error(f"Error updating progress: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@project_bp.route('/multi_project')
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

@project_bp.route('/chat')
def chat():
    project_name = request.args.get('project', 'Project')
    project_path, project_has_icon = get_project_icon_info(project_name)
    return render_template('chat.html', project_name=project_name, project_path=project_path, project_has_icon=project_has_icon)

@project_bp.route('/api/active')
def api_active():
    active = filter_ignored_projects(get_ui_active_windows())
    links = load_project_links()
    
    pinned_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pinned_quests.json')
    pinned_data = {}
    if os.path.exists(pinned_file):
        try:
            with open(pinned_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    pinned_data = {path: {"function": 0, "money": 0, "users": 0} for path in data}
                elif isinstance(data, dict):
                    pinned_data = data
        except:
            pass

    for win in active:
        p_path = win.get('path')
        if p_path:
            norm_path = os.path.normcase(os.path.normpath(p_path))
            win['dev_link'] = links.get(norm_path, "")
            win['is_pinned'] = norm_path in pinned_data
            win['progress'] = pinned_data.get(norm_path, {"function": 0, "money": 0, "users": 0})
        else:
            win['dev_link'] = ""
            win['is_pinned'] = False
            win['progress'] = {"function": 0, "money": 0, "users": 0}
    return jsonify(active)

@project_bp.route('/api/project_link', methods=['POST'])
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

@project_bp.route('/api/screenshot')
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

@project_bp.route('/get_icon')
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

@project_bp.route('/launch', methods=['POST'])
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

@project_bp.route('/focus', methods=['POST'])
def focus():
    title_to_find = request.json.get('title')
    project_name = focus_and_maximize_window(title_to_find)
    if project_name:
        return jsonify({'status': 'success', 'message': 'Focused', 'project_name': project_name})
    return jsonify({'status': 'error', 'message': 'Window not found'}), 404

@project_bp.route('/ignore', methods=['POST'])
def ignore_project():
    project_path = request.json.get('path')
    if project_path:
        save_ignored_folder(project_path)
        return jsonify({'status': 'success', 'message': 'Project ignored'})
    return jsonify({'status': 'error', 'message': 'Invalid path'}), 400

@project_bp.route('/api/ignored', methods=['GET'])
def get_ignored_route():
    return jsonify(load_ignored_folders())

@project_bp.route('/api/unignore', methods=['POST'])
def unignore_project_route():
    project_path = request.json.get('path')
    if not project_path:
        return jsonify({'status': 'error', 'message': 'Invalid path'}), 400
    
    ignored = load_ignored_folders()
    norm_target = os.path.normcase(os.path.normpath(project_path))
    new_ignored = [p for p in ignored if os.path.normcase(os.path.normpath(p)) != norm_target]
    
    try:
        ignored_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ignored_folders.json')
        with open(ignored_file_path, 'w', encoding='utf-8') as f:
            json.dump(new_ignored, f, indent=4)
        return jsonify({'status': 'success', 'message': 'Project unignored'})
    except Exception as e:
        logger.error(f"Failed to unignore project: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@project_bp.route('/api/multi_project_state', methods=['GET', 'POST'])
def multi_project_state_route():
    state_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'multi_project_state.json')
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

@project_bp.route('/api/projects_list')
def api_projects_list():
    projects = get_ui_projects_data()
    return jsonify(projects)