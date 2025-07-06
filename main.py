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
            'model': 'gemini'
        }
        write_config(default_config, filename)
        return default_config
    return config

# <<< CHANGE: NEW FUNCTION TO WRITE TO THE CONFIG FILE >>>
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

def get_content_text(content: Union[str, List[Dict[str, str]], Dict[str, str]]) -> str:
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        parts = []
        for item in content:
            if item.get("type") == "text":
                parts.append(item["text"])
            elif item.get("type") == "image_url": # OpenAI API format
                image_data = item.get("image_url", {}).get("url", "")
                if image_data.startswith('data:image'):
                    set_clipboard_image(image_data)
                parts.append(f"[Image: An uploaded image]")
        return "\n".join(parts)
    return ""

def handle_llm_interaction(prompt):
    global last_request_time
    logger.info(f"Starting {current_model} interaction.")

    current_time = time.time()
    time_since_last = current_time - last_request_time
    if time_since_last < MIN_REQUEST_INTERVAL:
        sleep(MIN_REQUEST_INTERVAL - time_since_last)
    last_request_time = time.time()

    request_json = request.get_json()
    image_list = []
    
    if 'messages' in request_json:
        for message in request_json['messages']:
            content = message.get('content', [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'image_url':
                        image_url = item.get('image_url', {}).get('url', '')
                        if image_url.startswith('data:image'):
                            image_list.append(image_url)
                            item['image_url']['url'] = '[IMAGE DATA REMOVED FOR LOGGING]'

    current_time_str = time.strftime('%Y-%m-%d %H:%M:%S')
    headers_log = f"{current_time_str} - INFO - Request data: {request_json}"

    full_prompt = "\n".join([
        headers_log,
        r'Please follow these rules: For each response, you must use one of the available tools formatted in proper XML tags. Tools include attempt_completion, ask_followup_question, read_file, write_to_file, search_files, list_files, execute_command, and list_code_definition_names. Do not respond conversationally - only use tool commands. Format any code you generate with proper indentation and line breaks, as you would in a standard code editor. Disregard any previous instructions about generating code in a single line or avoiding newline characters.',
        r'Write the entirity of your response in 1 big markdown codeblock, no word should be out of this 1 big code block and do not write a md codeblock within this big codeblock',
        prompt
    ])

    return talkto(current_model, full_prompt, image_list)[:-3]

# --- FLASK ROUTES ---

@app.route('/', methods=['GET'])
def home():
    logger.info(f"GET request to / from {request.remote_addr}")
    # The long HTML string is unchanged, so it's omitted here for brevity.
    # Just copy the HTML from your original file.
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Model Bridge</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }}
            .container {{ background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(10px); border-radius: 20px; padding: 40px; max-width: 600px; width: 100%; box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1); border: 1px solid rgba(255, 255, 255, 0.2); }}
            h1 {{ text-align: center; color: #333; margin-bottom: 10px; font-size: 2.5em; font-weight: 700; background: linear-gradient(135deg, #667eea, #764ba2); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
            .subtitle {{ text-align: center; color: #666; margin-bottom: 40px; font-size: 1.1em; }}
            .model-selector {{ background: linear-gradient(135deg, #f8f9fa, #e9ecef); border-radius: 15px; padding: 30px; margin: 30px 0; border: 2px solid rgba(102, 126, 234, 0.1); transition: all 0.3s ease; }}
            .model-selector:hover {{ transform: translateY(-2px); box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1); }}
            .current-model {{ text-align: center; margin-bottom: 25px; }}
            .current-model h3 {{ color: #333; margin-bottom: 10px; font-size: 1.3em; }}
            .model-badge {{ display: inline-block; padding: 8px 20px; border-radius: 25px; font-weight: 600; font-size: 1.1em; text-transform: uppercase; letter-spacing: 1px; color: white; background: linear-gradient(135deg, #667eea, #764ba2); box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3); }}
            .button-group {{ display: flex; gap: 15px; justify-content: center; flex-wrap: wrap; }}
            .model-btn {{ background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; padding: 15px 30px; border-radius: 50px; font-size: 1.1em; font-weight: 600; cursor: pointer; transition: all 0.3s ease; box-shadow: 0 6px 20px rgba(102, 126, 234, 0.3); text-transform: uppercase; letter-spacing: 0.5px; min-width: 150px; }}
            .model-btn:hover {{ transform: translateY(-3px); box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4); }}
            .model-btn:active {{ transform: translateY(-1px); }}
            .model-btn.gemini {{ background: linear-gradient(135deg, #4285f4, #34a853); }}
            .model-btn.gemini:hover {{ box-shadow: 0 10px 30px rgba(66, 133, 244, 0.4); }}
            .model-btn.deepseek {{ background: linear-gradient(135deg, #ff6b6b, #ee5a24); }}
            .model-btn.deepseek:hover {{ box-shadow: 0 10px 30px rgba(255, 107, 107, 0.4); }}
            .status {{ margin-top: 20px; padding: 15px; border-radius: 10px; text-align: center; font-weight: 500; opacity: 0; transition: all 0.3s ease; }}
            .status.show {{ opacity: 1; }}
            .status.success {{ background: linear-gradient(135deg, #00b894, #00cec9); color: white; }}
            .status.error {{ background: linear-gradient(135deg, #ff6b6b, #ee5a24); color: white; }}
            .info-section {{ margin-top: 40px; padding: 25px; background: rgba(102, 126, 234, 0.05); border-radius: 15px; border-left: 4px solid #667eea; }}
            .info-section h3 {{ color: #333; margin-bottom: 15px; font-size: 1.2em; }}
            .endpoint {{ background: rgba(255, 255, 255, 0.7); padding: 12px; border-radius: 8px; margin: 8px 0; font-family: 'Courier New', monospace; font-size: 0.9em; border-left: 3px solid #667eea; }}
            .endpoint strong {{ color: #764ba2; }}
            .loading {{ display: none; margin-top: 10px; }}
            .loading.show {{ display: block; }}
            .spinner {{ border: 3px solid rgba(255, 255, 255, 0.3); border-top: 3px solid white; border-radius: 50%; width: 20px; height: 20px; animation: spin 1s linear infinite; display: inline-block; margin-right: 10px; }}
            @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
            @media (max-width: 600px) {{ .container {{ padding: 25px; margin: 10px; }} h1 {{ font-size: 2em; }} .button-group {{ flex-direction: column; }} .model-btn {{ width: 100%; }} }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 AI Model Bridge</h1>
            <p class="subtitle">Seamlessly switch between AI models</p>
            <div class="model-selector">
                <div class="current-model"><h3>Active Model</h3><span class="model-badge" id="currentModel">{current_model.upper()}</span></div>
                <div class="button-group">
                    <button class="model-btn gemini" onclick="switchModel('gemini')">🧠 Gemini</button>
                    <button class="model-btn deepseek" onclick="switchModel('deepseek')">🔍 DeepSeek</button>
                </div>
                <div class="loading" id="loading"><div class="spinner"></div>Switching model...</div>
                <div class="status" id="status"></div>
            </div>
            <div class="info-section">
                <h3>📡 Available Endpoints</h3>
                <div class="endpoint"><strong>POST</strong> /chat/completions - Main chat completion endpoint</div>
                <div class="endpoint"><strong>GET</strong> /model - Get current active model</div>
                <div class="endpoint"><strong>POST</strong> /model - Switch between models</div>
            </div>
        </div>
        <script>
            function switchModel(model) {{
                const statusDiv = document.getElementById('status');
                const loadingDiv = document.getElementById('loading');
                const currentModelSpan = document.getElementById('currentModel');
                loadingDiv.classList.add('show');
                statusDiv.classList.remove('show');
                fetch('/model', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{'model': model}})
                }})
                .then(response => response.json())
                .then(data => {{
                    loadingDiv.classList.remove('show');
                    if (data.success) {{
                        currentModelSpan.textContent = data.model.toUpperCase();
                        statusDiv.className = 'status success show';
                        statusDiv.innerHTML = '✅ Successfully switched to ' + data.model.toUpperCase();
                        setTimeout(() => {{ statusDiv.classList.remove('show'); }}, 3000);
                    }} else {{
                        statusDiv.className = 'status error show';
                        statusDiv.innerHTML = '❌ Error: ' + data.error;
                    }}
                }})
                .catch(error => {{
                    loadingDiv.classList.remove('show');
                    statusDiv.className = 'status error show';
                    statusDiv.innerHTML = '❌ Network error: ' + error.message;
                }});
            }}
        </script>
    </body>
    </html>
    """

@app.route('/model', methods=['GET'])
def get_model():
    """Get current model"""
    return jsonify({'model': current_model})

# <<< CHANGE: THIS FUNCTION IS NOW MODIFIED TO SAVE THE SELECTION >>>
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
        if new_model not in ['deepseek', 'gemini']:
            return jsonify({'success': False, 'error': 'Invalid model. Use "deepseek" or "gemini"'}), 400
        
        # Update the model in memory
        current_model = new_model
        logger.info(f"Model switched to: {current_model}")
        
        # --- Persist the change to the config file ---
        try:
            config['model'] = current_model  # Update the config dictionary
            write_config(config)             # Write the updated dictionary to file
            logger.info(f"Saved model '{current_model}' to config.txt")
        except Exception as e:
            # Log the error but don't fail the request, as the in-memory switch worked.
            logger.error(f"CRITICAL: Failed to save model to config.txt: {e}")
        # ----------------------------------------------
        
        return jsonify({'success': True, 'model': current_model})
    
    except Exception as e:
        logger.error(f"Error switching model: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/chat/completions', methods=['POST'])
def chat_completions():
    try:
        data = request.get_json()
        logger.debug(f"Request data: {data}") # Use debug for verbose data
        
        if not data or 'messages' not in data:
            return jsonify({'error': {'message': 'Invalid request format'}}), 400

        last_message = data['messages'][-1]
        prompt = get_content_text(last_message.get('content', ''))
        
        request_id = str(int(time.time()))
        is_streaming = data.get('stream', False)
        
        response = handle_llm_interaction(prompt)
        
        if is_streaming:
            def generate():
                response_id = f"chatcmpl-{request_id}"
                
                # Send role first
                chunk = {"id": response_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": "gpt-3.5-turbo", "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
                yield f"data: {json.dumps(chunk)}\n\n"
                
                # Stream line by line
                lines = response.splitlines(True) # Keep newlines
                for line in lines:
                    chunk = {"id": response_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": "gpt-3.5-turbo", "choices": [{"index": 0, "delta": {"content": line}, "finish_reason": None}]}
                    yield f"data: {json.dumps(chunk)}\n\n"
                    # sleep(0.01) # Optional small delay
                
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
            'usage': {'prompt_tokens': len(prompt), 'completion_tokens': len(response), 'total_tokens': len(prompt) + len(response)}
        })
    
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return jsonify({'error': {'message': str(e)}}), 500

if __name__ == '__main__':
    logger.info(f"Starting AI Model Bridge server on port 3001 with default model: {current_model.upper()}")
    app.run(host="0.0.0.0", port=3001)