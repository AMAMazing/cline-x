from flask import Flask, jsonify, request, Response
import webbrowser
import win32clipboard
import time
import os
from optimisewaito import optimiseWait, set_autopath
import pyautogui
import logging
import json
from typing import Union, List, Dict, Optional

def set_clipboard(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text)
    win32clipboard.CloseClipboard()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
last_request_time = 0
MIN_REQUEST_INTERVAL = 5

set_autopath(r"D:\cline-x-claudeweb\images", resolution='1440p')
url = 'https://claude.ai/new'

def get_content_text(content: Union[str, List[Dict[str, str]], Dict[str, str]]) -> str:
    """Extract text from different content formats"""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        return " ".join(item["text"] for item in content if item.get("type") == "text")
    elif isinstance(content, dict):
        return content.get("text", "")
    return ""

def handle_claude_interaction(prompt):
    logger.info(f"Starting Claude interaction with prompt: {prompt}")
    
    # Open Claude in browser
    logger.info("Opening Claude in browser")
    webbrowser.open(url)
    time.sleep(2)
    
    # Wait for interface elements
    logger.info("Waiting for Claude interface elements...")
    result = optimiseWait(['claudenew', 'submit'], clicks=[1], xoff=[0,-100])
    logger.info(f"OptimiseWait result: {result}")
    
    if result['image'] == 'submit':
        time.sleep(0.5)
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('delete')

    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
    headers_log = f"{current_time} - {dict(request.headers)}\n"
    headers_log += f"{current_time} - INFO - Time since last request: {time.time() - last_request_time} seconds\n"
    headers_log += f"{current_time} - INFO - Request data: {request.get_json()}"
    
    # Send the prompt to Claude
    set_clipboard(headers_log)
    pyautogui.hotkey('ctrl','v')

    set_clipboard('Please follow these rules: For each response, you must use one of the available tools formatted in proper XML tags. Tools include attempt_completion, ask_followup_question, read_file, write_to_file, search_files, list_files, execute_command, and list_code_definition_names. Do not respond conversationally - only use tool commands: ')
    pyautogui.hotkey('ctrl','v')
    
    set_clipboard(prompt)
    pyautogui.hotkey('ctrl','v')
    
    optimiseWait('submit')
    optimiseWait('copy')
    
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
    
    return '\n'.join(cleaned_response)

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
                    time.sleep(0.1)
                
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