import time
import os
import subprocess
import logging
import threading
from modules.config_utils import read_config
from modules.vscode_utils import find_vscode_executable
from modules.window_manager import wait_for_vscode_window
from modules.chat_manager import add_chat_message
from modules.automation_utils import process_optimisewait_message
from modules.pomodoro_manager import pomodoro_state

logger = logging.getLogger(__name__)

state = {
    'system_busy': False,
    'global_completion_status': False,
    'global_last_reply': "",
    'current_queue_task': None,
}

task_queue = []
queue_lock = threading.Lock()

def process_next_queue_item(terminal_log_level='default'):
    config = read_config()
    timeout_minutes = int(config.get('queue_timeout_minutes', 5))
    wait_timeout = timeout_minutes * 60
    start_wait = time.time()
    
    while True:
        # Wait if the system is currently processing any LLM interaction
        while state['system_busy']:
            if time.time() - start_wait > wait_timeout:
                logger.warning("Queue wait timeout exceeded, proceeding with next task.")
                state['system_busy'] = False
                break
            time.sleep(2)
            
        with queue_lock:
            # Re-check inside lock to ensure another thread didn't beat us
            if state['system_busy']:
                continue
                
            if task_queue:
                state['current_queue_task'] = task_queue.pop(0)
                state['system_busy'] = True
                break # Got the task, exit the polling loop
            elif pomodoro_state['queue'] and pomodoro_state['is_break']:
                state['current_queue_task'] = pomodoro_state['queue'].pop(0)
                state['current_queue_task']['is_pomodoro'] = True
                pomodoro_state['current_task'] = state['current_queue_task']
                state['system_busy'] = True
                break

            state['current_queue_task'] = None
            return # No tasks left
    
    try:
        project_path = state['current_queue_task'].get('project_path')
        message = state['current_queue_task'].get('message')
        
        vscode_exe = find_vscode_executable()
        if vscode_exe and project_path and os.path.isdir(project_path):
            subprocess.Popen([vscode_exe, project_path], creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            project_name = os.path.basename(project_path)
            wait_for_vscode_window(project_name)
        
        time.sleep(1) # Extra stability wait
        
        state['global_completion_status'] = False
        state['global_last_reply'] = ""
        add_chat_message('user', message)
        process_optimisewait_message(message, debug=(terminal_log_level == 'debug'))
    except Exception as e:
        logger.error(f"Error processing queue item: {e}")
        state['system_busy'] = False
        state['current_queue_task'] = None
        # Reset Pomodoro active task tracking on error
        if pomodoro_state['current_task']:
            pomodoro_state['current_task'] = None
        threading.Thread(target=process_next_queue_item, args=(terminal_log_level,), daemon=True).start()