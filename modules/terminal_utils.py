import os
import sys
import colorama
from ascii import art as attempt_completion_art
from ascii import banner as bannertop

def terminal_link(path):
    """Creates a clickable link for terminal emulators that support OSC 8."""
    absolute_path = os.path.abspath(path).replace('\\', '/')
    if not absolute_path.startswith('/'):
        absolute_path = '/' + absolute_path
    
    # OSC 8 escape sequence
    return f"\033]8;;file://{absolute_path}\033\\{path}\033]8;;\033\\"

def clear_previous_alert(alert_state):
    """Clear any previous alert from the terminal using multiple methods."""
    if not alert_state['active'] or alert_state['lines_printed'] <= 0:
        return
    
    try:
        if os.name == 'nt':
            sys.stdout.write(f"\033[{alert_state['lines_printed']}A")
            sys.stdout.write("\033[J")
        else:
            sys.stdout.write(f"\x1b[{alert_state['lines_printed']}A")
            sys.stdout.write("\x1b[J")
        sys.stdout.flush()
    except Exception:
        try:
            terminal_height = os.get_terminal_size().lines
            print("\n" * min(alert_state['lines_printed'] + 5, terminal_height))
        except Exception:
            print("\n" * (alert_state['lines_printed'] + 3))
    
    alert_state['lines_printed'] = 0
    alert_state['active'] = False

def print_completion_alert(alert_state):
    """Prints a completion alert and tracks it for later clearing."""
    clear_previous_alert(alert_state)
    
    border_char = "#"
    border_width = 80
    border_top = colorama.Fore.YELLOW + colorama.Style.BRIGHT + (border_char * border_width)
    border_bottom = colorama.Fore.YELLOW + colorama.Style.BRIGHT + (border_char * border_width)
    colored_art = colorama.Fore.GREEN + colorama.Style.BRIGHT + attempt_completion_art + colorama.Style.RESET_ALL
    
    alert_lines = [
        "",
        border_top,
        *colored_art.strip().split('\n'),
        border_bottom,
        ""
    ]
    
    alert_state['lines_printed'] = len(alert_lines)
    alert_state['active'] = True
    
    for line in alert_lines:
        print(line)
    
    sys.stdout.flush()

def print_summary_alert(summary: str, add_chat_message_func):
    """Prints a summary message in a highlighted format."""
    add_chat_message_func('system', f"AI Summary: {summary}")
    
    border = colorama.Fore.CYAN + colorama.Style.BRIGHT + "=" * 60
    title = colorama.Fore.CYAN + colorama.Style.BRIGHT + "[INFO] AI Summary:"
    content = colorama.Fore.WHITE + colorama.Style.BRIGHT + summary
    
    alert_message = [
        "",
        border,
        title,
        content,
        border,
        ""
    ]
    
    for line in alert_message:
        print(line)
    
    sys.stdout.flush()

def print_startup_banner(current_model, current_theme, terminal_log_level, terminal_alert_level, ntfy_notification_level, tunnel_active, auth_required, ngrok_tunnel, API_KEY, APP_PATH):
    """Print a nice startup banner with all the important information"""
    colorama.init(autoreset=True)
    rules_path = os.path.join(APP_PATH, "unified_rules.txt")
    
    banner = f"\n{bannertop}\n\n{colorama.Fore.YELLOW + colorama.Style.BRIGHT}[INFO] SERVER INFORMATION:{colorama.Style.RESET_ALL}\n   {colorama.Fore.WHITE}Local:  {colorama.Fore.CYAN + colorama.Style.BRIGHT}http://127.0.0.1:3001{colorama.Style.RESET_ALL}"
    
    if tunnel_active:
        banner += f"\n   {colorama.Fore.WHITE}Remote: {colorama.Fore.GREEN + colorama.Style.BRIGHT}{ngrok_tunnel.public_url if ngrok_tunnel else 'Starting...'}{colorama.Style.RESET_ALL}"
    
    if auth_required:
        banner += f"\n   {colorama.Fore.WHITE}API Key: {colorama.Fore.MAGENTA + colorama.Style.BRIGHT}{API_KEY}{colorama.Style.RESET_ALL}"
    
    clickable_rules_path = terminal_link(rules_path)

    banner += f"""

{colorama.Fore.YELLOW + colorama.Style.BRIGHT}[CONFIG] CURRENT SETTINGS:{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Model: {colorama.Fore.GREEN + colorama.Style.BRIGHT}{current_model.upper()}{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Theme: {colorama.Fore.GREEN + colorama.Style.BRIGHT}{current_theme.capitalize()}{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Terminal Output: {colorama.Fore.GREEN + colorama.Style.BRIGHT}{terminal_log_level.capitalize()}{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Terminal Alerts: {colorama.Fore.GREEN + colorama.Style.BRIGHT}{terminal_alert_level.capitalize()}{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Push Notifications: {colorama.Fore.GREEN + colorama.Style.BRIGHT}{ntfy_notification_level.capitalize()}{colorama.Style.RESET_ALL}

{colorama.Fore.YELLOW + colorama.Style.BRIGHT}[FILES] SYSTEM RULES:{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Unified Rules: {colorama.Fore.CYAN + colorama.Style.BRIGHT}{clickable_rules_path}{colorama.Style.RESET_ALL}
   {colorama.Style.DIM}(Ctrl+Click the path above to edit rules directly){colorama.Style.RESET_ALL}

{colorama.Fore.YELLOW + colorama.Style.BRIGHT}[PANEL] CONTROL PANEL:{colorama.Style.RESET_ALL}
   {colorama.Fore.WHITE}Open your browser and go to:{colorama.Style.RESET_ALL}
   {colorama.Fore.CYAN + colorama.Style.BRIGHT + colorama.Back.BLACK}  http://127.0.0.1:3001  {colorama.Style.RESET_ALL}
   
   {colorama.Fore.WHITE}Tip: Use the 'Open Rules in Editor' button in the dashboard for quick access!{colorama.Style.RESET_ALL}

{colorama.Fore.CYAN + colorama.Style.BRIGHT}{'=' * 62}{colorama.Style.RESET_ALL}
"""
    print(banner)