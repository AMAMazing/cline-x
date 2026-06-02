import os
import json
import logging
from modules.vscode_utils import load_ignored_folders, find_project_icon
from modules.project_utils import get_ui_projects_data

logger = logging.getLogger(__name__)

PROJECT_LINKS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'project_links.json')

def load_project_links():
    if os.path.exists(PROJECT_LINKS_FILE):
        try:
            with open(PROJECT_LINKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading project links: {e}")
            return {}
    return {}

def save_project_links(links_data):
    try:
        with open(PROJECT_LINKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(links_data, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving project links: {e}")

def filter_ignored_projects(items):
    ignored = load_ignored_folders()
    if not ignored:
        return items
    ignored_norm = [os.path.normcase(os.path.normpath(p)) for p in ignored]
    return [item for item in items if not item.get('path') or os.path.normcase(os.path.normpath(item['path'])) not in ignored_norm]

def get_all_projects_with_ignore_state():
    projects = get_ui_projects_data()
    ignored = load_ignored_folders()
    
    if not ignored:
        for p in projects:
            p['is_ignored'] = False
        return projects
        
    ignored_norm = [os.path.normcase(os.path.normpath(p)) for p in ignored]
    project_paths_norm = set()
    
    for p in projects:
        p_path = p.get('path')
        if p_path:
            norm_p = os.path.normcase(os.path.normpath(p_path))
            p['is_ignored'] = norm_p in ignored_norm
            project_paths_norm.add(norm_p)
        else:
            p['is_ignored'] = False
            
    # Add any ignored folders that are not currently in the projects list (because they were filtered out upstream)
    for ig_path in ignored:
        norm_ig = os.path.normcase(os.path.normpath(ig_path))
        if norm_ig not in project_paths_norm:
            icon_path = find_project_icon(ig_path)
            projects.append({
                'name': os.path.basename(ig_path) or ig_path,
                'path': ig_path,
                'has_icon': bool(icon_path and os.path.exists(icon_path)),
                'is_ignored': True
            })
            project_paths_norm.add(norm_ig)
            
    # Sort projects so that ignored ones appear at the beginning, preserving existing order otherwise.
    projects.sort(key=lambda x: not x.get('is_ignored', False))
            
    return projects