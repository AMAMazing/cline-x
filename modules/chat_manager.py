import time
import os
import json
import logging
from typing import List, Dict, Optional
from modules.config_utils import APP_PATH

logger = logging.getLogger(__name__)

CHAT_STORAGE_PATH = os.path.join(APP_PATH, 'chat_history.json')
MAX_MESSAGES_PER_SESSION = 200
MAX_SESSIONS_PER_PROJECT = 50

# Fast in-memory state tracking
current_active_project = "default"
current_active_session_id = "default"
chat_history: List[Dict] = []

def _load_storage() -> Dict:
    if os.path.exists(CHAT_STORAGE_PATH):
        try:
            with open(CHAT_STORAGE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading {CHAT_STORAGE_PATH}: {e}")
    return {}

def _save_storage(data: Dict):
    try:
        with open(CHAT_STORAGE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving {CHAT_STORAGE_PATH}: {e}")

def set_active_project_and_session(project_name: str, session_id: Optional[str] = None):
    global current_active_project, current_active_session_id, chat_history
    current_active_project = project_name or "default"
    
    storage = _load_storage()
    proj_data = storage.setdefault(current_active_project, {"sessions": {}, "active_session": "default"})
    
    if session_id:
        current_active_session_id = session_id
        proj_data["active_session"] = session_id
    else:
        current_active_session_id = proj_data.get("active_session", "default")
    
    if current_active_session_id not in proj_data["sessions"]:
        proj_data["sessions"][current_active_session_id] = {
            "id": current_active_session_id,
            "title": "Initial Session",
            "created_at": time.strftime('%Y-%m-%d %H:%M:%S'),
            "updated_at": time.strftime('%Y-%m-%d %H:%M:%S'),
            "messages": []
        }
        _save_storage(storage)
        
    chat_history = proj_data["sessions"][current_active_session_id].get("messages", [])

def get_project_sessions(project_name: str) -> List[Dict]:
    storage = _load_storage()
    proj_data = storage.get(project_name or "default", {"sessions": {}})
    sessions_dict = proj_data.get("sessions", {})
    
    if not sessions_dict:
        # Create initial session for this project
        initial_sid = "default"
        sessions_dict[initial_sid] = {
            "id": initial_sid,
            "title": "Initial Session",
            "created_at": time.strftime('%Y-%m-%d %H:%M:%S'),
            "updated_at": time.strftime('%Y-%m-%d %H:%M:%S'),
            "messages": []
        }
        proj_data["sessions"] = sessions_dict
        proj_data["active_session"] = initial_sid
        storage[project_name or "default"] = proj_data
        _save_storage(storage)
    
    sessions_list = []
    for sid, sinfo in sessions_dict.items():
        messages = sinfo.get("messages", [])
        last_msg = messages[-1]["text"] if messages else ""
        first_user_msg = next((m["text"] for m in messages if m.get("role") == "user"), "")
        title = sinfo.get("title") or (first_user_msg[:40] + ("..." if len(first_user_msg) > 40 else "")) or "Conversation"
        
        sessions_list.append({
            "id": sid,
            "title": title,
            "created_at": sinfo.get("created_at", ""),
            "updated_at": sinfo.get("updated_at", ""),
            "message_count": len(messages),
            "last_message": last_msg[:80] + ("..." if len(last_msg) > 80 else ""),
            "is_active": (sid == proj_data.get("active_session"))
        })
    
    sessions_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return sessions_list

def create_project_session(project_name: str, title: Optional[str] = None) -> str:
    global current_active_project, current_active_session_id, chat_history
    current_active_project = project_name or "default"
    session_id = f"sess_{int(time.time())}"
    
    storage = _load_storage()
    proj_data = storage.setdefault(current_active_project, {"sessions": {}, "active_session": session_id})
    
    if len(proj_data["sessions"]) >= MAX_SESSIONS_PER_PROJECT:
        sorted_keys = sorted(proj_data["sessions"].keys(), key=lambda k: proj_data["sessions"][k].get("updated_at", ""))
        for k in sorted_keys[:len(proj_data["sessions"]) - MAX_SESSIONS_PER_PROJECT + 1]:
            if k != session_id:
                del proj_data["sessions"][k]

    proj_data["sessions"][session_id] = {
        "id": session_id,
        "title": title or "New Session",
        "created_at": time.strftime('%Y-%m-%d %H:%M:%S'),
        "updated_at": time.strftime('%Y-%m-%d %H:%M:%S'),
        "messages": []
    }
    proj_data["active_session"] = session_id
    _save_storage(storage)
    
    current_active_session_id = session_id
    chat_history = []
    return session_id

def delete_project_session(project_name: str, session_id: str) -> bool:
    storage = _load_storage()
    proj_data = storage.get(project_name or "default", {})
    sessions = proj_data.get("sessions", {})
    
    if session_id in sessions:
        del sessions[session_id]
        if proj_data.get("active_session") == session_id:
            remaining_keys = list(sessions.keys())
            proj_data["active_session"] = remaining_keys[0] if remaining_keys else "default"
            if not remaining_keys:
                sessions["default"] = {
                    "id": "default",
                    "title": "Initial Session",
                    "created_at": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "updated_at": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "messages": []
                }
        _save_storage(storage)
        return True
    return False

def get_project_messages(project_name: str, session_id: Optional[str] = None) -> List[Dict]:
    storage = _load_storage()
    proj_data = storage.get(project_name or "default", {})
    sessions = proj_data.get("sessions", {})
    
    target_sid = session_id or proj_data.get("active_session", "default")
    if target_sid in sessions:
        return sessions[target_sid].get("messages", [])
    return []

def get_ongoing_context_prompt(project_name: str, limit_messages: int = 6) -> str:
    messages = get_project_messages(project_name)
    if not messages:
        return ""
    
    recent = messages[-limit_messages:]
    context_lines = [
        "--- ONGOING PROJECT CONTEXT (from previous tasks/chat) ---",
        f"Project: {project_name}"
    ]
    
    for m in recent:
        role = "User" if m.get("role") == "user" else "Cline/Assistant"
        text = m.get("text", "").strip()
        if len(text) > 300:
            text = text[:300] + "..."
        context_lines.append(f"{role}: {text}")
        
    context_lines.append("--- END ONGOING CONTEXT ---\n")
    return "\n".join(context_lines)

def add_chat_message(role, text, full_text=None, project_name=None, session_id=None):
    global chat_history, current_active_project, current_active_session_id
    
    target_proj = project_name or current_active_project or "default"
    
    storage = _load_storage()
    proj_data = storage.setdefault(target_proj, {"sessions": {}, "active_session": "default"})
    target_sess = session_id or proj_data.get("active_session") or "default"
    
    message = {
        'id': f"msg_{int(time.time() * 1000)}",
        'role': role,
        'text': text,
        'time': time.strftime('%H:%M'),
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    if full_text:
        message['full_text'] = full_text

    try:
        sess_data = proj_data["sessions"].setdefault(target_sess, {
            "id": target_sess,
            "title": text[:40] if role == 'user' else "Conversation",
            "created_at": time.strftime('%Y-%m-%d %H:%M:%S'),
            "updated_at": time.strftime('%Y-%m-%d %H:%M:%S'),
            "messages": []
        })
        
        if role == 'user' and (sess_data.get("title") in ["New Session", "Initial Session", "Conversation", ""] or not sess_data.get("title")):
            clean_t = text.replace('\n', ' ').strip()
            sess_data["title"] = clean_t[:45] + ("..." if len(clean_t) > 45 else "")
            
        sess_data["updated_at"] = time.strftime('%Y-%m-%d %H:%M:%S')
        sess_messages = sess_data.setdefault("messages", [])
        sess_messages.append(message)
        
        if len(sess_messages) > MAX_MESSAGES_PER_SESSION:
            sess_messages.pop(0)
            
        proj_data["active_session"] = target_sess
        _save_storage(storage)
        
        if target_proj == current_active_project and target_sess == current_active_session_id:
            chat_history = sess_messages
    except Exception as e:
        logger.error(f"Error persisting chat message: {e}")