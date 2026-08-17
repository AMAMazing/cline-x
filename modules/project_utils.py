import os
import json
import time
import subprocess
import threading
from modules.vscode_utils import get_vscode_projects, load_ignored_folders, find_project_icon, get_active_windows

expo_process_logs = {}
expo_process_status = {}
expo_active_processes = {}

def detect_project_type(project_path):
    if not project_path or not os.path.exists(project_path):
        return 'unknown'
        
    try:
        if os.path.exists(os.path.join(project_path, 'next.config.js')) or \
           os.path.exists(os.path.join(project_path, 'next.config.mjs')):
            return 'nextjs'
            
        pkg_json_path = os.path.join(project_path, 'package.json')
        if os.path.exists(pkg_json_path):
            try:
                with open(pkg_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    deps = data.get('dependencies', {})
                    dev_deps = data.get('devDependencies', {})
                    if 'expo' in deps or 'expo' in dev_deps:
                        return 'expojs'
                    if 'next' in deps or 'next' in dev_deps:
                        return 'nextjs'
                    if 'react' in deps or 'react' in dev_deps:
                        return 'react'
            except Exception:
                pass
                
        if os.path.exists(os.path.join(project_path, 'setup.py')) or \
           os.path.exists(os.path.join(project_path, 'setup.cfg')):
            return 'pypi'
            
        if os.path.exists(os.path.join(project_path, 'requirements.txt')) or \
           os.path.exists(os.path.join(project_path, 'pyproject.toml')) or \
           os.path.exists(os.path.join(project_path, 'main.py')) or \
           os.path.exists(os.path.join(project_path, 'app.py')) or \
           os.path.exists(os.path.join(project_path, '.venv')) or \
           os.path.exists(os.path.join(project_path, 'venv')):
            return 'python'
            
        if os.path.exists(pkg_json_path):
            return 'nodejs'
            
    except Exception:
        pass
        
    return 'unknown'

def get_expo_settings_path(project_path):
    if not project_path:
        return None
    return os.path.join(project_path, '.expo', 'settings.json')

def get_expo_url_randomness(project_path):
    settings_file = get_expo_settings_path(project_path)
    if settings_file and os.path.exists(settings_file):
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('urlRandomness') or data.get('urlrandomness')
        except Exception:
            return None
    return None

def get_expo_tunnel_url(project_path):
    randomness = get_expo_url_randomness(project_path)
    if randomness:
        clean_random = str(randomness).strip().lower()
        if clean_random.startswith('http://') or clean_random.startswith('https://'):
            return clean_random
        return f"https://{clean_random}-anonymous-8081.exp.direct/"
    return None

def is_expo_running(project_path):
    if not project_path:
        return False
    norm_path = os.path.normcase(os.path.normpath(project_path))
    proc = expo_active_processes.get(norm_path)
    if proc and proc.poll() is None:
        return True
    return False

def get_active_expo_project():
    for norm_path, proc in list(expo_active_processes.items()):
        if proc and proc.poll() is None:
            return norm_path
    return None

def stream_expo_output(proc, norm_path, project_path):
    try:
        for line in iter(proc.stdout.readline, ''):
            if not line:
                break
            line_clean = line.strip()
            if line_clean:
                if norm_path not in expo_process_logs:
                    expo_process_logs[norm_path] = []
                expo_process_logs[norm_path].append(line_clean)
                if len(expo_process_logs[norm_path]) > 60:
                    expo_process_logs[norm_path].pop(0)
                
                if 'Tunnel ready' in line_clean or 'Tunnel connected' in line_clean:
                    url = get_expo_tunnel_url(project_path)
                    expo_process_status[norm_path]['state'] = 'ready'
                    expo_process_status[norm_path]['message'] = 'Tunnel ready!'
                    expo_process_status[norm_path]['url'] = url
                elif 'Starting Metro Bundler' in line_clean or 'Metro waiting' in line_clean:
                    expo_process_status[norm_path]['state'] = 'starting'
                    expo_process_status[norm_path]['message'] = 'Metro Bundler starting...'
                elif 'Starting project' in line_clean:
                    expo_process_status[norm_path]['state'] = 'starting'
                    expo_process_status[norm_path]['message'] = 'Starting project...'
    except Exception:
        pass

def start_expo_tunnel_process(project_path):
    norm_path = os.path.normcase(os.path.normpath(project_path))
    
    existing_proc = expo_active_processes.get(norm_path)
    if existing_proc and existing_proc.poll() is None:
        return existing_proc
        
    expo_process_logs[norm_path] = [f"Starting tunnel in: {project_path}"]
    expo_process_status[norm_path] = {
        'state': 'starting',
        'message': 'Starting Expo tunnel...',
        'url': None
    }
    
    cmd = 'npx.cmd expo start --tunnel' if os.name == 'nt' else 'npx expo start --tunnel'
    proc = subprocess.Popen(
        cmd,
        cwd=project_path,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    expo_active_processes[norm_path] = proc
    
    thread = threading.Thread(target=stream_expo_output, args=(proc, norm_path, project_path), daemon=True)
    thread.start()
    return proc

def stop_expo_tunnel_process(project_path):
    norm_path = os.path.normcase(os.path.normpath(project_path))
    proc = expo_active_processes.get(norm_path)
    if proc:
        try:
            if os.name == 'nt':
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                proc.terminate()
        except Exception:
            pass
        expo_active_processes.pop(norm_path, None)
    
    expo_process_status[norm_path] = {
        'state': 'stopped',
        'message': 'Tunnel stopped',
        'url': None
    }
    if norm_path in expo_process_logs:
        expo_process_logs[norm_path].append("[Tunnel stopped by user]")
    return True

def ensure_expo_tunnel_url(project_path, timeout=30):
    norm_path = os.path.normcase(os.path.normpath(project_path))
    
    if not is_expo_running(project_path):
        start_expo_tunnel_process(project_path)
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        time.sleep(1)
        url = get_expo_tunnel_url(project_path)
        status = expo_process_status.get(norm_path, {})
        if url and (status.get('state') == 'ready' or time.time() - start_time > 5):
            if norm_path in expo_process_status:
                expo_process_status[norm_path]['state'] = 'ready'
                expo_process_status[norm_path]['url'] = url
            return url
    return get_expo_tunnel_url(project_path)

def get_ui_projects_data():
    all_projects = get_vscode_projects()
    ignored_folders = load_ignored_folders()
    visible_projects = [p for p in all_projects if p not in ignored_folders]
    
    projects_data = []
    for p in visible_projects:
        projects_data.append({
            'path': p,
            'name': os.path.basename(p),
            'has_icon': find_project_icon(p) is not None,
            'project_type': detect_project_type(p)
        })
    return projects_data

def get_ui_active_windows():
    active_windows = get_active_windows()
    all_projects = get_vscode_projects()
    
    for win in active_windows:
        win['has_icon'] = False
        win['path'] = "" 
        win['project_type'] = "unknown"
        matched_proj = next((p for p in all_projects if os.path.basename(p) == win['name']), None)
        if matched_proj:
            win['path'] = matched_proj
            win['project_type'] = detect_project_type(matched_proj)
            if find_project_icon(matched_proj):
                win['has_icon'] = True
    return active_windows

def get_project_icon_info(project_name):
    all_projects = get_vscode_projects()
    project_path = ""
    project_has_icon = False
    
    matched_proj = next((p for p in all_projects if os.path.basename(p) == project_name), None)
    if matched_proj:
        project_path = matched_proj
        if find_project_icon(matched_proj):
            project_has_icon = True
            
    return project_path, project_has_icon