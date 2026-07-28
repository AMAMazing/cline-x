import os
import json
import logging
from datetime import date

logger = logging.getLogger(__name__)

POMODORO_STATS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pomodoro_stats.json')

pomodoro_state = {
    'queue': [],
    'completed': [],
    'is_break': False,
    'current_task': None,
    'break_started_at': None,
    'sprint_size': 0
}

def load_pomodoro_stats():
    defaults = {
        'total_sprints': 0,
        'total_tasks_completed': 0,
        'streak_days': 0,
        'best_streak': 0,
        'last_sprint_date': None,
        'daily_counts': {}
    }
    if os.path.exists(POMODORO_STATS_FILE):
        try:
            with open(POMODORO_STATS_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                defaults.update(loaded)
        except Exception:
            pass
    return defaults

def save_pomodoro_stats(stats):
    try:
        with open(POMODORO_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving pomodoro stats: {e}")

def record_sprint_completion(task_count):
    """Called once a full pomodoro batch finishes. Updates streaks/totals."""
    if task_count <= 0:
        return
    stats = load_pomodoro_stats()
    today = date.today()
    today_str = today.isoformat()

    last_date_str = stats.get('last_sprint_date')
    if last_date_str:
        try:
            last_date = date.fromisoformat(last_date_str)
            delta_days = (today - last_date).days
        except Exception:
            delta_days = None

        if delta_days == 0:
            pass  # already logged a sprint today, streak unchanged
        elif delta_days == 1:
            stats['streak_days'] = stats.get('streak_days', 0) + 1
        else:
            stats['streak_days'] = 1
    else:
        stats['streak_days'] = 1

    stats['best_streak'] = max(stats.get('best_streak', 0), stats['streak_days'])
    stats['last_sprint_date'] = today_str
    stats['total_sprints'] = stats.get('total_sprints', 0) + 1
    stats['total_tasks_completed'] = stats.get('total_tasks_completed', 0) + task_count

    daily_counts = stats.get('daily_counts', {})
    daily_counts[today_str] = daily_counts.get(today_str, 0) + 1
    stats['daily_counts'] = daily_counts

    save_pomodoro_stats(stats)