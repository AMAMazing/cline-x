import os
import sys
import json

def get_app_path():
    """Get the appropriate path for the application's data files."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        # Move up one level since we are in the 'modules' directory now
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

APP_PATH = get_app_path()
DOTENV_PATH = os.path.join(APP_PATH, '.env')
IGNORED_FILE = os.path.join(APP_PATH, 'ignored_folders.json')

def get_config_path():
    return os.path.join(APP_PATH, "clinex_config.json")

def read_config():
    """Reads the configuration file and returns a dictionary."""
    config = {}
    config_path = get_config_path()
    old_config_path = os.path.join(APP_PATH, "config.txt")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except Exception as e:
            print(f"Error reading clinex_config.json: {e}")

    elif os.path.exists(old_config_path):
        try:
            with open(old_config_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip().strip('"').strip("'")
        except Exception:
            pass
            
    defaults = {
        'model': 'gemini',
        'theme': 'dark',
        'ntfy_topic': '',
        'ntfy_notification_level': 'none',
        'terminal_log_level': 'default',
        'terminal_alert_level': 'none',
        'tunnel_active': 'False',
        'auth_required': 'False'
    }
    
    for k, v in defaults.items():
        if k not in config:
            config[k] = v
            
    return config

def write_config(config_data):
    """Writes the configuration dictionary to the specified file."""
    with open(get_config_path(), 'w') as f:
        json.dump(config_data, f, indent=4)

def get_rules_content():
    """Reads the unified rules from an external file."""
    rules_path = os.path.join(APP_PATH, "unified_rules.txt")
    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"ERROR: '{rules_path}' not found. Please create this file with your system prompt.")
        return "You are a helpful AI assistant."
    except Exception as e:
        print(f"ERROR reading rules file: {e}")
        return "You are a helpful AI assistant."