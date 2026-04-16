import os
from modules.vscode_utils import get_vscode_projects, load_ignored_folders, find_project_icon, get_active_windows

def get_ui_projects_data():
    """
    Retrieves and formats project data for the dashboard and multi-project views.
    Returns a list of dictionaries with 'path', 'name', and 'has_icon'.
    """
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
        matched_proj = next((p for p in all_projects if os.path.basename(p) == win['name']), None)
        if matched_proj:
            win['path'] = matched_proj
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