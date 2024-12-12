from flask import Flask, jsonify, request, Response
import webbrowser
import win32clipboard
import time
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

def read_config(filename="config.txt"):
    config = {}
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            if '=' in line:  # Only process lines that contain an '='
                key, value = line.split('=', 1)  # Split only at the first '='
                # Strip whitespace and quotes, then convert to proper string
                config[key.strip()] = str(value.strip().strip('"').strip("'"))
    return config

config = read_config()
autorun = config.get('autorun')

def set_clipboard(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    try:
        win32clipboard.SetClipboardText(str(text))
    except Exception:
        # Fallback for Unicode characters
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, str(text).encode('utf-16le'))
    win32clipboard.CloseClipboard()

def set_clipboard_image(image_data):
    """Set image data to clipboard"""
    try:
        # Decode base64 image
        binary_data = base64.b64decode(image_data.split(',')[1])
        
        # Convert to bitmap using PIL
        image = Image.open(io.BytesIO(binary_data))
        
        # Convert to bitmap format
        output = io.BytesIO()
        image.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]  # Remove bitmap header
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
    """Extract base64 image data from text"""
    pattern = r'data:image\/[^;]+;base64,[a-zA-Z0-9+/]+=*'
    match = re.search(pattern, text)
    return match.group(0) if match else None

def handle_save_dialog():
    optimiseWait(['save', 'runcommand','resume','approve','startnewtask'],clicks=[1,1,1,1,0],altpath=None)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
last_request_time = 0
MIN_REQUEST_INTERVAL = 5  # Minimum time between new tab creation

set_autopath(r"D:\cline-x-claudeweb\images")
set_altpath(r"D:\cline-x-claudeweb\images\alt1440")

def get_content_text(content: Union[str, List[Dict[str, str]], Dict[str, str]]) -> str:
    """Extract text and handle images from different content formats"""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        parts = []
        for item in content:
            if item.get("type") == "text":
                parts.append(item["text"])
            elif item.get("type") == "image":
                # Extract image data and description
                image_data = item.get("image_url", {}).get("url", "")  # For base64 images
                if not image_data and "data" in item:  # For binary image data
                    image_data = base64.b64encode(item["data"]).decode('utf-8')
                
                # Set image to clipboard if it's base64 data
                if image_data.startswith('data:image'):
                    set_clipboard_image(image_data)
                
                # Add image reference to text with description if available
                description = item.get("description", "An uploaded image")
                parts.append(f"[Image: {description}]")
        
        return "\n".join(parts)
    elif isinstance(content, dict):
        text = content.get("text", "")
        if content.get("type") == "image":
            image_data = content.get("image_url", {}).get("url", "")
            if not image_data and "data" in content:
                image_data = base64.b64encode(content["data"]).decode('utf-8')
            if image_data.startswith('data:image'):
                set_clipboard_image(image_data)
            description = content.get("description", "An uploaded image")
            return f"[Image: {description}]"
        return text
    return ""

def handle_claude_interaction(prompt):
    global last_request_time
    
    logger.info(f"Starting Claude interaction with prompt: {prompt}")
    
    # Check if enough time has passed since last request
    current_time = time.time()
    time_since_last = current_time - last_request_time
    
    if time_since_last < MIN_REQUEST_INTERVAL:
        sleep(MIN_REQUEST_INTERVAL - time_since_last)
    
    # Open Claude in browser and update last request time
    logger.info("Opening gemini in browser")
    url = 'https://aistudio.google.com/prompts/new_chat'
    webbrowser.open(url)
    last_request_time = time.time()

    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
    headers_log = f"{current_time} - {dict(request.headers)}\n"
    headers_log += f"{current_time} - INFO - Time since last request: {time_since_last} seconds\n"
    request_json = request.get_json()
    
    optimiseWait('typesmthn')

    # Extract and handle base64 images before logging
    if 'messages' in request_json:
        for message in request_json['messages']:
            content = message.get('content', [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'image_url':
                        image_url = item.get('image_url', {}).get('url', '')
                        if image_url.startswith('data:image'):
                            set_clipboard_image(image_url)
                            pyautogui.hotkey('ctrl','v')
                            # Remove image data from logs
                            item['image_url']['url'] = '[IMAGE DATA REMOVED]'
    
    headers_log += f"{current_time} - INFO - Request data: {request_json}"

    # Send instructions to Claude
    set_clipboard(headers_log)
    pyautogui.hotkey('ctrl','v')

    set_clipboard('Please follow these rules: For each response, you must use one of the available tools formatted in proper XML tags. Tools include attempt_completion, ask_followup_question, read_file, write_to_file, search_files, list_files, execute_command, and list_code_definition_names. Do not respond conversationally - only use tool commands: ')
    pyautogui.hotkey('ctrl','v')

    set_clipboard(prompt)
    pyautogui.hotkey('ctrl','v')

    optimiseWait('run')
    
    sleep(1)
    print('copying now')

    optimiseWait('copy')
    
    pyautogui.hotkey('ctrl','w')
    
    pyautogui.hotkey('alt','tab')

    print('closed')
    sleep(1)
    print('waitdone')

    # Get Claude's response
    win32clipboard.OpenClipboard()
    response = win32clipboard.GetClipboardData()
    win32clipboard.CloseClipboard()
    
    # Clean up the response - preserve \n in code blocks
    cleaned_response = []
    in_code_block = False
    xml_tags = ['<write_to_file>', '</write_to_file>', '<content>', '</content>']
    
    for line in response.splitlines():
        if any(tag in line for tag in xml_tags):
            in_code_block = '<content>' in line or (in_code_block and '</content>' not in line)
            cleaned_response.append(line)
        else:
            if in_code_block:
                # Preserve line as-is in code blocks
                cleaned_response.append(line)
            else:
                # Replace escaped newlines outside code blocks
                cleaned_response.append(line.replace('\\n', '\n'))

    final_response = '\n'.join(cleaned_response)
    
    # Schedule the save dialog to be handled after response is returned
    if autorun == "True":
        print('TRUE')
        Timer(0.5, handle_save_dialog).start()
    else:
        print('autorun false')
    
    return final_response

@app.route('/', methods=['GET'])
def home():
    logger.info(f"GET request to / from {request.remote_addr}")
    return "Claude API Bridge"

@app.route('/chat/completions', methods=['POST'])
def chat_completions():
    try:
        data = request.get_json()
        logger.info(f"Request data: {data}")
        
        if not data or 'messages' not in data:
            return jsonify({'error': {'message': 'Invalid request format'}}), 400

        # Get the last message's content, handling complex formats
        last_message = data['messages'][-1]
        prompt = get_content_text(last_message.get('content', ''))
        
        request_id = str(int(time.time()))
        is_streaming = data.get('stream', False)
        
        # Handle the Claude interaction
        response = handle_claude_interaction(prompt)
        
        if is_streaming:
            def generate():
                response_id = f"chatcmpl-{request_id}"
                
                # Send role first
                chunk = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "gpt-3.5-turbo",
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant"},
                        "finish_reason": None
                    }]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                
                # Stream line by line for XML and code content
                lines = response.splitlines()
                for line in lines:
                    chunk = {
                        "id": response_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "gpt-3.5-turbo",
                        "choices": [{
                            "index": 0,
                            "delta": {"content": line + "\n"},
                            "finish_reason": None
                        }]
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                    sleep(0.1)
                
                # End stream
                chunk = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "gpt-3.5-turbo",
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"
            
            return Response(generate(), mimetype='text/event-stream')
        
        return jsonify({
            'id': f'chatcmpl-{request_id}',
            'object': 'chat.completion',
            'created': int(time.time()),
            'model': 'gpt-3.5-turbo',
            'choices': [{
                'index': 0,
                'message': {
                    'role': 'assistant',
                    'content': response
                },
                'finish_reason': 'stop'
            }],
            'usage': {
                'prompt_tokens': len(prompt),
                'completion_tokens': len(response),
                'total_tokens': len(prompt) + len(response)
            }
        })
    
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return jsonify({'error': {'message': str(e)}}), 500

if __name__ == '__main__':
    logger.info("Starting Claude API Bridge server on port 3000")
    app.run(host="0.0.0.0", port=3000)
