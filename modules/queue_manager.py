import time
import os
import logging
import threading
from typing import Optional, Dict, Any, List
from modules.config_utils import read_config
from modules.chat_manager import add_chat_message
from modules.cline_cli_utils import run_cline_cli_process, terminate_active_cline
from modules.pomodoro_manager import pomodoro_state

logger = logging.getLogger(__name__)

state: Dict[str, Any] = {
    'system_busy': False,
    'global_completion_status': False,
    'global_last_reply': "",
    'current_queue_task': None,
    'last_stdout_chunk': "",
}

task_queue: List[Dict[str, Any]] = []
queue_lock = threading.Lock()

def _handle_cline_stdout_line(line: str, project_name: Optional[str] = None):
    line_clean = line.strip()
    if line_clean:
        state['last_stdout_chunk'] = line_clean
        state['global_last_reply'] = line_clean
        logger.debug(f"[Cline CLI stdout] {line_clean}")

def _handle_cline_stderr_line(line: str):
    line_clean = line.strip()
    if line_clean:
        logger.warning(f"[Cline CLI stderr] {line_clean}")

def _on_cline_task_complete(return_code: int, stdout_text: str, stderr_text: str, terminal_log_level: str):
    logger.info(f"Task completed with exit code {return_code}")
    
    output_summary = stdout_text.strip() if stdout_text.strip() else ("Task completed." if return_code == 0 else f"Failed with code {return_code}")
    # Extract last few lines if long
    summary_lines = [l for l in output_summary.splitlines() if l.strip()]
    brief_summary = summary_lines[-1] if summary_lines else output_summary
    
    state['system_busy'] = False
    state['global_completion_status'] = (return_code == 0)
    state['global_last_reply'] = brief_summary

    current_task = state.get('current_queue_task')
    proj_name = current_task.get('project_name') if current_task else "default"

    # Add assistant response to chat history
    add_chat_message('assistant', brief_summary, full_text=stdout_text or stderr_text, project_name=proj_name)

    # Update Pomodoro state if linked
    if current_task and current_task.get('is_pomodoro'):
        current_task['result'] = brief_summary
        pomodoro_state['completed'].append(current_task)
        pomodoro_state['current_task'] = None

    state['current_queue_task'] = None

    # Trigger next item in queue
    threading.Thread(target=process_next_queue_item, args=(terminal_log_level,), daemon=True).start()

def process_next_queue_item(terminal_log_level: str = 'default'):
    config = read_config()
    timeout_minutes = int(config.get('queue_timeout_minutes', 5))
    wait_timeout = timeout_minutes * 60
    start_wait = time.time()
    
    while True:
        while state['system_busy']:
            if time.time() - start_wait > wait_timeout:
                logger.warning("Queue wait timeout exceeded, terminating active process and proceeding.")
                terminate_active_cline()
                state['system_busy'] = False
                break
            time.sleep(1)
            
        with queue_lock:
            if state['system_busy']:
                continue
                
            if task_queue:
                state['current_queue_task'] = task_queue.pop(0)
                state['system_busy'] = True
                break
            elif pomodoro_state['queue'] and pomodoro_state['is_break']:
                state['current_queue_task'] = pomodoro_state['queue'].pop(0)
                state['current_queue_task']['is_pomodoro'] = True
                pomodoro_state['current_task'] = state['current_queue_task']
                state['system_busy'] = True
                break

            state['current_queue_task'] = None
            return

    try:
        task = state['current_queue_task']
        project_path = task.get('project_path')
        project_name = task.get('project_name') or "default"
        message = task.get('message', '')
        yolo_mode = bool(task.get('yolo', True))
        
        state['global_completion_status'] = False
        state['global_last_reply'] = "Executing via Cline CLI..."
        
        logger.info(f"Processing queue item for project '{project_name}' in '{project_path}'")
        
        run_cline_cli_process(
            prompt=message,
            cwd=project_path,
            yolo=yolo_mode,
            on_stdout_line=lambda line: _handle_cline_stdout_line(line, project_name),
            on_stderr_line=_handle_cline_stderr_line,
            on_complete=lambda code, out, err: _on_cline_task_complete(code, out, err, terminal_log_level)
        )
    except Exception as e:
        logger.error(f"Error executing queue item via Cline CLI: {e}")
        state['system_busy'] = False
        state['current_queue_task'] = None
        if pomodoro_state.get('current_task'):
            pomodoro_state['current_task'] = None
        threading.Thread(target=process_next_queue_item, args=(terminal_log_level,), daemon=True).start()