from flask import Flask, jsonify, request, Response
import webbrowser
import win32clipboard
import time
import pywintypes
from time import sleep
import os
from optimisewait import optimiseWait, set_autopath, set_altpath
import pyautogui
import logging
import json
from threading import Timer
from typing import Union, List, Dict, Optional
import base64
import io
from PIL import Image
import re
from talktollm import talkto
import requests # Added for sending notifications

# --- CONFIGURATION HANDLING ---

def read_config(filename="config.txt"):
    """Reads the configuration file and returns a dictionary."""
    config = {}
    try:
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        # If config.txt doesn't exist, create it with default values
        print(f"'{filename}' not found. Creating with default settings.")
        default_config = {
            'autorun': 'False',
            'usefirefox': 'False',
            'model': 'gemini',
            'debug_mode': 'False',
            'ntfy_topic': '',
            'ntfy_notification_level': 'none',
            'theme': 'dark' # Added: light, dark
        }
        write_config(default_config, filename)
        return default_config
    return config

def write_config(config_data, filename="config.txt"):
    """Writes the configuration dictionary to the specified file."""
    with open(filename, 'w') as f:
        for key, value in config_data.items():
            # Write in key = "value" format for consistency
            f.write(f'{key} = "{value}"\n')

# Load initial configuration
config = read_config()
autorun = config.get('autorun')
usefirefox = config.get('usefirefox', 'False') == 'True'

# Model configuration - default to gemini if not in config
current_model = config.get('model', 'gemini')

# Read debug mode from config, default to False. Convert to boolean.
debug_mode = config.get('debug_mode', 'False').lower() == 'true'

# Read notification level from config, default to 'completion'.
ntfy_notification_level = config.get('ntfy_notification_level', 'none')

# Read theme from config, default to 'light'
current_theme = config.get('theme', 'dark')


# --- NTFY NOTIFICATION ---

def send_ntfy_notification(topic: str, simple_title: str, full_content: str, tags: str = "tada"):
    """
    Sends a push notification via ntfy.sh with a simple title and detailed content.

    Args:
        topic (str): The ntfy.sh URL topic to publish to.
        simple_title (str): The short message to be displayed as the notification title.
        full_content (str): The full message content, visible inside the ntfy app.
        tags (str): Comma-separated list of ntfy tags (emojis).
    """
    # Only proceed if the user has configured an ntfy topic in config.txt
    if not topic:
        logger.info("ntfy_topic not configured. Skipping notification.")
        return

    try:
        # Send an HTTP POST request to the ntfy topic URL
        response = requests.post(
            topic,
            # The main body of the request contains the full, detailed message from the AI
            data=full_content.encode('utf-8'),
            headers={
                # The 'Title' header sets the simple, visible notification title
                # FIX: Encode the title to UTF-8 to prevent UnicodeEncodeError with emojis
                "Title": simple_title.encode('utf-8'),
                # 'Priority' makes the notification stand out on the device
                "Priority": "high",
                # 'Tags' adds an emoji icon to the notification
                "Tags": tags
            }
        )
        # Check if the request was successful (e.g., status code 200)
        response.raise_for_status()
        logger.info(f"Successfully sent ntfy notification to topic: {topic}")
    except requests.exceptions.RequestException as e:
        # Log an error if the notification fails to send
        logger.error(f"Failed to send ntfy notification: {e}")


# --- CLIPBOARD AND UTILITY FUNCTIONS ---

def set_clipboard(text, retries=3, delay=0.2):
    for i in range(retries):
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            try:
                win32clipboard.SetClipboardText(str(text))
            except Exception:
                win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, str(text).encode('utf-16le'))
            win32clipboard.CloseClipboard()
            return
        except pywintypes.error as e:
            if e.winerror == 5:
                print(f"Clipboard access denied. Retrying... (Attempt {i+1}/{retries})")
                time.sleep(delay)
            else:
                raise
        except Exception as e:
            raise
    print(f"Failed to set clipboard after {retries} attempts.")

def set_clipboard_image(image_data):
    try:
        binary_data = base64.b64decode(image_data.split(',')[1])
        image = Image.open(io.BytesIO(binary_data))
        output = io.BytesIO()
        image.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]
        output.close()
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        print(f"Error setting image to clipboard: {e}")
        return False

def extract_base64_image(text):
    pattern = r'data:image\/[^;]+;base64,[a-zA-Z0-9+/]+=*'
    match = re.search(pattern, text)
    return match.group(0) if match else None

# --- LOGGING AND FLASK APP SETUP ---

logging.basicConfig(
    level=logging.INFO, # Changed to INFO for less verbose production logs
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
last_request_time = 0
MIN_REQUEST_INTERVAL = 5

set_autopath(r"D:\cline-x-claudeweb\images")
set_altpath(r"D:\cline-x-claudeweb\images\alt1440")

# --- CORE LOGIC FUNCTIONS ---

def extract_images_from_text(text: str) -> tuple[str, list[str]]:
    """
    Extracts base64 image data from text content and returns cleaned text + image list.
    
    Args:
        text: The text content that may contain embedded image data
        
    Returns:
        tuple: (cleaned_text, image_list)
            - cleaned_text: Text with image data removed and replaced with placeholders
            - image_list: List of data URIs for images found
    """
    image_list = []
    
    # This pattern seems to be for a different format, but we'll keep it.
    # The primary extraction happens in get_content_text_and_images for OpenAI format.
    pattern = re.compile(
        r'media_type.*?[\'\\"](?P<mtype>image/[a-zA-Z]+)[\'\\"]'
        r'.*?'
        r'data.*?[\'\\"](?P<base64>[a-zA-Z0-9+/=]{50,})[\'\\"]',
        re.DOTALL
    )
    
    matches = list(pattern.finditer(text))
    
    # Build list of unique images (deduplicate)
    seen = set()
    for match in matches:
        media_type = match.group('mtype')
        base64_data = match.group('base64')
        if media_type and base64_data:
            full_data_uri = f"data:{media_type};base64,{base64_data}"
            if full_data_uri not in seen:
                image_list.append(full_data_uri)
                seen.add(full_data_uri)
    
    # Remove image data from text, replace with placeholder
    cleaned_text = text
    if matches:
        # Only replace if custom pattern matches were found
        for i, match in enumerate(matches):
            cleaned_text = cleaned_text.replace(match.group(0), f"[Image {i+1} uploaded]", 1)
    
    return cleaned_text, image_list


def get_content_text_and_images(content) -> tuple[str, list[str]]:
    """
    Extracts text and images from message content.
    Handles both string content and structured list content (OpenAI API format).
    
    Returns:
        tuple: (text_content, image_list)
    """
    image_list = []
    
    if isinstance(content, str):
        # Content is a string - extract embedded images using regex
        text, images = extract_images_from_text(content)
        return text, images
        
    elif isinstance(content, list):
        # Content is structured list (OpenAI API format)
        text_parts = []
        image_count = 0
        for item in content:
            if item.get("type") == "text":
                # Extract any embedded images from text parts too
                text, images = extract_images_from_text(item.get("text", ""))
                text_parts.append(text)
                image_list.extend(images)
                
            elif item.get("type") == "image_url":
                # Handle OpenAI API format image_url
                image_data = item.get("image_url", {}).get("url", "")
                if image_data.startswith('data:image'):
                    image_list.append(image_data)
                    image_count += 1
                    # Use a placeholder that won't be confused with the text content
                    text_parts.append(f"[Image {image_count} uploaded]")
                    
        return "\n".join(text_parts), list(set(image_list)) # Deduplicate images
        
    return "", []


# Replace the existing get_content_text function with this:
def get_content_text(content):
    """Legacy function - use get_content_text_and_images instead"""
    text, _ = get_content_text_and_images(content)
    return text


# Updated handle_llm_interaction function
def handle_llm_interaction(prompt_text, image_list=None, request_data_for_log=None):
    """
    Handles the interaction with the LLM, including prompt construction,
    logging, and cleaning of repeated context.
    """
    global last_request_time
    logger.info(f"Starting {current_model} interaction. Debug mode is {'ON' if debug_mode else 'OFF'}.")

    current_time = time.time()
    time_since_last = current_time - last_request_time
    if time_since_last < MIN_REQUEST_INTERVAL:
        sleep(MIN_REQUEST_INTERVAL - time_since_last)
    last_request_time = time.time()

    current_time_str = time.strftime('%Y-%m-%d %H:%M:%S')

    # Create detailed log header with sanitized JSON request data
    if request_data_for_log:
        try:
            # Create a deep copy to avoid modifying the original request object
            log_data = json.loads(json.dumps(request_data_for_log))
            if 'messages' in log_data:
                for message in log_data['messages']:
                    content = message.get('content', [])
                    if isinstance(content, list):
                        for item in content:
                            if item.get('type') == 'image_url':
                                if 'image_url' in item and 'url' in item['image_url']:
                                    item['image_url']['url'] = '[IMAGE DATA REMOVED FOR LOGGING]'
            headers_log = f"{current_time_str} - INFO - Request data: {json.dumps(log_data)}"
        except Exception as e:
            logger.error(f"Failed to create sanitized log data: {e}")
            headers_log = f"{current_time_str} - INFO - Request received with {len(image_list or [])} image(s). (Log sanitization failed)"
    else:
        headers_log = f"{current_time_str} - INFO - Request received with {len(image_list or [])} image(s)"

    # FIX: De-duplicate repeating context blocks sent by the client.
    # The client can sometimes send multiple <environment_details> blocks. We only want the last one.
    context_block_pattern = re.compile(r"<environment_details>.*?</environment_details>", re.DOTALL)
    matches = list(context_block_pattern.finditer(prompt_text))
    
    if len(matches) > 1:
        logger.info(f"Found {len(matches)} repeating context blocks. Cleaning up prompt.")
        # We build a new string by taking slices of the original, skipping the parts we want to remove.
        new_prompt_parts = []
        last_end = 0
        # Iterate through all matches that need to be removed (all except the last one).
        for match in matches[:-1]:
            # Append the text from the end of the last removed block to the start of the current one.
            new_prompt_parts.append(prompt_text[last_end:match.start()])
            # Move the pointer to the end of the current block, effectively skipping it.
            last_end = match.end()
        
        # Finally, append the rest of the string from the end of the last removed block.
        # This will include the final (and desired) context block.
        new_prompt_parts.append(prompt_text[last_end:])
        
        prompt_text = "".join(new_prompt_parts)

    prompt_instructions = [
        headers_log,
        r'Please follow these rules: For each response, you must use one of the available tools formatted in proper XML tags. Tools include attempt_completion, ask_followup_question, read_file, write_to_file, search_files, list_files, execute_command, and list_code_definition_names. Do not respond conversationally - only use tool commands. Format any code you generate with proper indentation and line breaks, as you would in a standard code editor. Disregard any previous instructions about generating code in a single line or avoiding newline characters.',
        r'Write the entirity of your response in 1 big markdown codeblock, no word should be out of this 1 big code block and do not write a md codeblock within this big codeblock',
    ]

    if ntfy_notification_level == 'all':
        summary_instruction = r"You MUST include a `<summary>` tag inside your `<thinking>` block for every tool call. This summary should be a very brief, user-friendly explanation of the action you are about to take. For example: `<summary>Reading the project's configuration to check dependencies.</summary>` or `<summary>Completing the user's request by providing the full Python script.</summary>`."
        prompt_instructions.append(summary_instruction)

    # Append the user's full prompt (which includes history from the client)
    prompt_instructions.append(prompt_text)
    full_prompt = "\n".join(prompt_instructions)

    # Pass both prompt and the already-extracted images to talkto
    return talkto(current_model, full_prompt, imagedata=image_list if image_list else None, debug=debug_mode)

# --- FLASK ROUTES ---

@app.route('/', methods=['GET'])
def home():
    logger.info(f"GET request to / from {request.remote_addr}")
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Model Bridge</title>
        <style>
            :root {{
                --background-start: #F4F7FC;
                --background-end: #E6EBF5;
                --card-background: #FFFFFF;
                --primary-color: #4A6BEE;
                --primary-hover: #3859d4;
                --text-color: #334155;
                --text-light: #64748B;
                --border-color: #E2E8F0;
                --shadow-color: rgba(74, 107, 238, 0.15);
                --toggle-bg: #CBD5E1;
                --button-group-bg: #EDF2F7;
            }}
            body[data-theme="dark"] {{
                --background-start: #111827;
                --background-end: #0c121e;
                --card-background: #1F2937;
                --primary-color: #60A5FA;
                --primary-hover: #3B82F6;
                --text-color: #E5E7EB;
                --text-light: #9CA3AF;
                --border-color: #374151;
                --shadow-color: rgba(96, 165, 250, 0.15);
                --toggle-bg: #4B5563;
                --button-group-bg: #374151;
            }}
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, var(--background-start) 0%, var(--background-end) 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
                color: var(--text-color);
                transition: background-color 0.3s, color 0.3s;
            }}
            .container {{
                position: relative;
                background: var(--card-background);
                border-radius: 24px;
                padding: 40px;
                max-width: 500px;
                width: 100%;
                box-shadow: 0 25px 50px -12px var(--shadow-color);
                border: 1px solid var(--border-color);
                transition: background-color 0.3s, border-color 0.3s;
            }}
            h1 {{
                text-align: center;
                margin-bottom: 8px;
                font-size: 2.25em;
                font-weight: 700;
                background: linear-gradient(135deg, var(--primary-color), #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            .subtitle {{
                text-align: center;
                color: var(--text-light);
                margin-bottom: 40px;
                font-size: 1.1em;
            }}
            .control-section {{
                margin-bottom: 30px;
            }}
            .control-section h3 {{
                font-size: 1.1em;
                font-weight: 600;
                margin-bottom: 16px;
                color: var(--text-color);
            }}
            .button-group {{
                display: flex;
                gap: 10px;
                justify-content: center;
                flex-wrap: wrap;
                background-color: var(--button-group-bg);
                border-radius: 12px;
                padding: 6px;
                border: 1px solid var(--border-color);
            }}
            .model-btn {{
                flex: 1;
                background: transparent;
                color: var(--text-light);
                border: none;
                padding: 12px 10px;
                border-radius: 9px;
                font-size: 0.9em;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                white-space: nowrap;
            }}
            .model-btn:hover {{
                color: var(--primary-color);
                background-color: rgba(74, 107, 238, 0.1);
            }}
            .model-btn.active {{
                background: var(--primary-color);
                color: white;
                box-shadow: 0 4px 12px var(--shadow-color);
            }}
            .model-btn.active:hover {{
                background: var(--primary-hover);
            }}
            .settings-row {{
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .toggle-switch {{
                position: relative;
                display: inline-block;
                width: 50px;
                height: 28px;
            }}
            .toggle-switch input {{
                opacity: 0;
                width: 0;
                height: 0;
            }}
            .slider {{
                position: absolute;
                cursor: pointer;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background-color: var(--toggle-bg);
                transition: .4s;
                border-radius: 28px;
            }}
            .slider:before {{
                position: absolute;
                content: "";
                height: 20px;
                width: 20px;
                left: 4px;
                bottom: 4px;
                background-color: white;
                transition: .4s;
                border-radius: 50%;
            }}
            input:checked + .slider {{
                background-color: var(--primary-color);
            }}
            input:checked + .slider:before {{
                transform: translateX(22px);
            }}
            .theme-toggle {{
                position: absolute;
                top: 20px;
                right: 20px;
                background: none;
                border: none;
                cursor: pointer;
                padding: 8px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-light);
                transition: color 0.2s, background-color 0.2s;
            }}
            .theme-toggle:hover {{
                background-color: var(--button-group-bg);
            }}
            .theme-toggle svg {{
                width: 20px;
                height: 20px;
            }}
            .theme-toggle .sun-icon {{ display: none; }}
            .theme-toggle .moon-icon {{ display: block; }}
            body[data-theme="dark"] .theme-toggle .sun-icon {{ display: block; }}
            body[data-theme="dark"] .theme-toggle .moon-icon {{ display: none; }}
        </style>
    </head>
    <body data-theme="{current_theme}">
        <div class="container">
            <button class="theme-toggle" onclick="toggleTheme()" aria-label="Toggle theme">
                <svg
                class="sun-icon" 
  xmlns="http://www.w3.org/2000/svg"
  width="24"
  height="24"
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
>
  <circle cx="12" cy="12" r="5" />
  <line x1="12" y1="1" x2="12" y2="3" />
  <line x1="12" y1="21" x2="12" y2="23" />
  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
  <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
  <line x1="1" y1="12" x2="3" y2="12" />
  <line x1="21" y1="12" x2="23" y2="12" />
  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
  <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
</svg>

<svg class="moon-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path fill-rule="evenodd" d="M9.528 1.718a.75.75 0 01.162.819A8.97 8.97 0 009 6a9 9 0 009 9 8.97 8.97 0 003.463-.69a.75.75 0 01.981.98 10.503 10.503 0 01-9.694 6.46c-5.799 0-10.5-4.701-10.5-10.5 0-3.51 1.713-6.635 4.342-8.532a.75.75 0 01.818.162z" clip-rule="evenodd"></path></svg>
            </button>
            <h1>🤖 AI Bridge</h1>
            <p class="subtitle">Switch models and settings instantly.</p>
            
            <div class="control-section">
                <h3>Active Model</h3>
                <div class="button-group" id="model-group">
                    <button class="model-btn {'active' if current_model == 'gemini' else ''}" onclick="switchModel(this, 'gemini')">🧠 Gemini</button>
                    <button class="model-btn {'active' if current_model == 'deepseek' else ''}" onclick="switchModel(this, 'deepseek')">🔍 DeepSeek</button>
                    <button class="model-btn {'active' if current_model == 'aistudio' else ''}" onclick="switchModel(this, 'aistudio')">🎨 AIStudio</button>
                </div>
            </div>

            <div class="control-section">
                 <div class="settings-row">
                    <h3>Debug Mode</h3>
                    <label class="toggle-switch">
                        <input type="checkbox" id="debugToggle" {'checked' if debug_mode else ''} onchange="setDebug(this.checked)">
                        <span class="slider"></span>
                    </label>
                 </div>
            </div>

            <div class="control-section">
                <h3>Notification Level</h3>
                <div class="button-group" id="notification-group">
                    <button class="model-btn {'active' if ntfy_notification_level == 'none' else ''}" onclick="setNotificationLevel(this, 'none')">None</button>
                    <button class="model-btn {'active' if ntfy_notification_level == 'completion' else ''}" onclick="setNotificationLevel(this, 'completion')">Completions</button>
                    <button class="model-btn {'active' if ntfy_notification_level == 'all' else ''}" onclick="setNotificationLevel(this, 'all')">All Responses</button>
                </div>
            </div>
        </div>

        <script>
            function updateActiveButton(groupElement, clickedButton) {{
                groupElement.querySelectorAll('.model-btn').forEach(btn => {{
                    btn.classList.remove('active');
                }});
                clickedButton.classList.add('active');
            }}
            
            function switchModel(btn, model) {{
                updateActiveButton(document.getElementById('model-group'), btn);
                fetch('/model', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{'model': model}})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (!data.success) {{
                        console.error('Error: ' + data.error);
                    }}
                }})
                .catch(error => console.error('Network error: ' + error.message));
            }}

            function setDebug(state) {{
                fetch('/debug', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{'debug': state}})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (!data.success) {{
                        console.error('Failed to save debug state:', data.error);
                        document.getElementById('debugToggle').checked = !state;
                    }}
                }})
                .catch(error => {{
                    console.error('Network error saving debug state:', error);
                    document.getElementById('debugToggle').checked = !state;
                }});
            }}

            function setNotificationLevel(btn, level) {{
                updateActiveButton(document.getElementById('notification-group'), btn);
                fetch('/notifications', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{'level': level}})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (!data.success) {{
                        console.error('Error: ' + data.error);
                    }}
                }})
                .catch(error => console.error('Network error: ' + error.message));
            }}
            
            function setTheme(theme) {{
                document.body.dataset.theme = theme;
                fetch('/theme', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{'theme': theme}})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (!data.success) {{
                        console.error('Failed to save theme:', data.error);
                        const revertedTheme = theme === 'dark' ? 'light' : 'dark';
                        document.body.dataset.theme = revertedTheme;
                    }}
                }})
                .catch(error => {{
                    console.error('Network error saving theme:', error);
                    const revertedTheme = theme === 'dark' ? 'light' : 'dark';
                    document.body.dataset.theme = revertedTheme;
                }});
            }}

            function toggleTheme() {{
                const currentTheme = document.body.dataset.theme;
                const newTheme = currentTheme === 'light' ? 'dark' : 'light';
                setTheme(newTheme);
            }}
        </script>
    </body>
    </html>
    """

@app.route('/model', methods=['GET'])
def get_model():
    """Get current model"""
    return jsonify({'model': current_model})

@app.route('/model', methods=['POST'])
def switch_model():
    """Switch between models and save the choice to config.txt."""
    global current_model
    global config
    
    try:
        data = request.get_json()
        if not data or 'model' not in data:
            return jsonify({'success': False, 'error': 'Model not specified'}), 400
        
        new_model = data['model'].lower()
        if new_model not in ['deepseek', 'gemini', 'aistudio']:
            return jsonify({'success': False, 'error': 'Invalid model. Use "deepseek", "gemini", or "aistudio"'}), 400
        
        current_model = new_model
        logger.info(f"Model switched to: {current_model}")
        
        try:
            config['model'] = current_model
            write_config(config)
            logger.info(f"Saved model '{current_model}' to config.txt")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to save model to config.txt: {e}")
        
        return jsonify({'success': True, 'model': current_model})
    
    except Exception as e:
        logger.error(f"Error switching model: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/debug', methods=['GET', 'POST'])
def toggle_debug_mode():
    """Get or set the debug mode status and save it to config.txt."""
    global debug_mode
    global config

    if request.method == 'GET':
        return jsonify({'debug_mode': debug_mode})
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            if data is None or 'debug' not in data or not isinstance(data['debug'], bool):
                return jsonify({'success': False, 'error': 'Invalid request. Send {"debug": true} or {"debug": false}'}), 400

            new_state = data['debug']
            debug_mode = new_state
            status = "ON" if debug_mode else "OFF"
            logger.info(f"Debug mode set to: {status}")

            try:
                config['debug_mode'] = str(debug_mode)
                write_config(config)
                logger.info(f"Saved debug_mode='{debug_mode}' to config.txt")
            except Exception as e:
                logger.error(f"CRITICAL: Failed to save debug_mode to config.txt: {e}")

            return jsonify({'success': True, 'debug_mode': debug_mode})

        except Exception as e:
            logger.error(f"Error setting debug mode: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/notifications', methods=['GET', 'POST'])
def notification_settings():
    """Get or set the ntfy notification level and save it to config.txt."""
    global ntfy_notification_level
    global config

    if request.method == 'GET':
        return jsonify({'level': ntfy_notification_level})
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            if data is None or 'level' not in data:
                return jsonify({'success': False, 'error': 'Invalid request. Send {"level": "level_name"}'}), 400
            
            new_level = data['level'].lower()
            if new_level not in ['none', 'completion', 'all']:
                return jsonify({'success': False, 'error': 'Invalid level. Use "none", "completion", or "all".'}), 400

            ntfy_notification_level = new_level
            logger.info(f"Notification level set to: {ntfy_notification_level}")

            try:
                config['ntfy_notification_level'] = ntfy_notification_level
                write_config(config)
                logger.info(f"Saved ntfy_notification_level='{ntfy_notification_level}' to config.txt")
            except Exception as e:
                logger.error(f"CRITICAL: Failed to save notification level to config.txt: {e}")

            return jsonify({'success': True, 'level': ntfy_notification_level})

        except Exception as e:
            logger.error(f"Error setting notification level: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/theme', methods=['GET', 'POST'])
def theme_settings():
    """Get or set the UI theme and save it to config.txt."""
    global current_theme
    global config

    if request.method == 'GET':
        return jsonify({'theme': current_theme})
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            if data is None or 'theme' not in data:
                return jsonify({'success': False, 'error': 'Invalid request. Send {"theme": "theme_name"}'}), 400
            
            new_theme = data['theme'].lower()
            if new_theme not in ['light', 'dark']:
                return jsonify({'success': False, 'error': 'Invalid theme. Use "light" or "dark".'}), 400

            current_theme = new_theme
            logger.info(f"Theme set to: {current_theme}")

            try:
                config['theme'] = current_theme
                write_config(config)
                logger.info(f"Saved theme='{current_theme}' to config.txt")
            except Exception as e:
                logger.error(f"CRITICAL: Failed to save theme to config.txt: {e}")

            return jsonify({'success': True, 'theme': current_theme})

        except Exception as e:
            logger.error(f"Error setting theme: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500


# Updated chat_completions route
@app.route('/chat/completions', methods=['POST'])
def chat_completions():
    try:
        data = request.get_json()
        logger.debug(f"Request data received")
        
        if not data or 'messages' not in data:
            return jsonify({'error': {'message': 'Invalid request format'}}), 400

        last_message = data['messages'][-1]
        
        # Use the new function to separate text and images
        prompt_text, image_list = get_content_text_and_images(last_message.get('content', ''))
        
        if image_list:
            logger.info(f"Extracted {len(image_list)} image(s) from the prompt")
        
        request_id = str(int(time.time()))
        is_streaming = data.get('stream', False)
        
        # Call the updated handle_llm_interaction with separated data and original data for logging
        response = handle_llm_interaction(prompt_text, image_list, request_data_for_log=data)
        
        # Check notification settings and send notifications accordingly
        ntfy_topic = config.get('ntfy_topic', '')
        
        if ntfy_notification_level == 'all':
            summary_match = re.search(r"<summary>(.*?)</summary>", response, re.DOTALL)
            summary = summary_match.group(1).strip() if summary_match else None

            if "<attempt_completion>" in response:
                send_ntfy_notification(
                    topic=ntfy_topic,
                    simple_title="Cline-x: Task Completion",
                    full_content=summary or "Task completion submitted.",
                    tags="tada"
                )
            elif summary:
                send_ntfy_notification(
                    topic=ntfy_topic,
                    simple_title="🤖 Cline-x: AI Response",
                    full_content=summary,
                    tags="robot_face"
                )
        elif ntfy_notification_level == 'completion' and "<attempt_completion>" in response:
            send_ntfy_notification(
                topic=ntfy_topic,
                simple_title="Cline-x: Task Completion 🎉",
                full_content=response,
                tags="tada"
            )
        
        if is_streaming:
            def generate():
                response_id = f"chatcmpl-{request_id}"
                
                # Send role first
                chunk = {"id": response_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": "gpt-3.5-turbo", "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
                yield f"data: {json.dumps(chunk)}\n\n"
                
                # Stream line by line
                lines = response.splitlines(True)
                for line in lines:
                    chunk = {"id": response_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": "gpt-3.5-turbo", "choices": [{"index": 0, "delta": {"content": line}, "finish_reason": None}]}
                    yield f"data: {json.dumps(chunk)}\n\n"
                
                # End stream
                chunk = {"id": response_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": "gpt-3.5-turbo", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"
            
            return Response(generate(), mimetype='text/event-stream')
        
        return jsonify({
            'id': f'chatcmpl-{request_id}',
            'object': 'chat.completion',
            'created': int(time.time()),
            'model': 'gpt-3.5-turbo',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': response}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': len(prompt_text), 'completion_tokens': len(response), 'total_tokens': len(prompt_text) + len(response)}
        })
    
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return jsonify({'error': {'message': str(e)}}), 500

if __name__ == '__main__':
    logger.info(f"Starting AI Model Bridge server on port 3001 with default model: {current_model.upper()}")
    app.run(host="0.0.0.0", port=3001)