import os
import json
from modules.vscode_utils import get_vscode_projects, load_ignored_folders, find_project_icon, get_active_windows

def detect_project_type(project_path):
    if not project_path or not os.path.exists(project_path):
        return 'unknown'
        
    try:
        # Check Next.js configs
        if os.path.exists(os.path.join(project_path, 'next.config.js')) or \
           os.path.exists(os.path.join(project_path, 'next.config.mjs')):
            return 'nextjs'
            
        # Check package.json for specific dependencies
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
                
        # Check PyPI (Before standard Python)
        if os.path.exists(os.path.join(project_path, 'setup.py')) or \
           os.path.exists(os.path.join(project_path, 'setup.cfg')):
            return 'pypi'
            
        # Check Python
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

def get_ui_projects_data():
    """
    Retrieves and formats project data for the dashboard and multi-project views.
    Returns a list of dictionaries with 'path', 'name', 'has_icon', and 'project_type'.
    """
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
    """
    Retrieves active windows and matches them with VS Code projects to find icons.
    """
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
    """
    Finds a specific project's path and icon status by its basename.
    """
    all_projects = get_vscode_projects()
    project_path = ""
    project_has_icon = False
    
    matched_proj = next((p for p in all_projects if os.path.basename(p) == project_name), None)
    if matched_proj:
        project_path = matched_proj
        if find_project_icon(matched_proj):
            project_has_icon = True
            
    return project_path, project_has_icon