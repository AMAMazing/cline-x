from flask import Flask, jsonify, request
import webbrowser
import win32clipboard
import win32con
import time
import os
from optimisewait import optimiseWait, set_autopath
import pyautogui
import logging

def set_clipboard(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text)
    win32clipboard.CloseClipboard()

# Set up logging to show everything in terminal
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
last_request_time = 0
MIN_REQUEST_INTERVAL = 5  # Minimum seconds between requests

set_autopath(r"D:\cline-x-claudeweb\images")
url = 'https://claude.ai/new'

def handle_claude_interaction(prompt):
    """Only called when we receive an actual API request"""
    logger.info(f"Starting Claude interaction with prompt: {prompt}")
    
    # Extract text content from prompt if it's a list of dictionaries
    if isinstance(prompt, list):
        prompt_text = ""
        for item in prompt:
            if isinstance(item, dict) and 'text' in item:
                prompt_text += item['text'] + "\n"
        prompt = prompt_text.strip()
    
    # Open Claude in browser
    logger.info("Opening Claude in browser")
    webbrowser.open(url)
    time.sleep(2)  # Wait for browser to open
    
    # Wait for either claudenew or submit to appear
    logger.info("Waiting for Claude interface elements...")
    result = optimiseWait(['claudenew', 'submit'], clicks=[1], xoff=[0,-100])
    logger.info(f"OptimiseWait result: {result}")
    
    if result['image'] == 'submit':
        time.sleep(0.5)
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('delete')

    # Get the current time for the log entry timestamp
    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
    headers_log = f"{current_time} - INFO - Headers: {dict(request.headers)}\n"
    headers_log += f"{current_time} - INFO - Time since last request: {time.time() - last_request_time} seconds\n"
    headers_log += f"{current_time} - INFO - Request data: {request.get_json()}"
    
    set_clipboard(headers_log)
    pyautogui.hotkey('ctrl','v')
    set_clipboard(prompt)
    pyautogui.hotkey('ctrl','v')
    #pyautogui.press('enter')
    # TODO: Add response capture logic here
    time.sleep(10)
    return "Response placeholder"

@app.route('/', methods=['GET'])
def home():
    logger.info(f"GET request to / from {request.remote_addr}")
    return "Claude API Bridge"

@app.route('/chat/completions', methods=['POST'])
def chat_completions():
    global last_request_time
    
    try:
        # Log request details
        logger.info(f"POST request to /chat/completions from {request.remote_addr}")
        logger.info(f"Headers: {dict(request.headers)}")
        
        # Rate limiting
        current_time = time.time()
        time_since_last = current_time - last_request_time
        logger.info(f"Time since last request: {time_since_last} seconds")
        
        if time_since_last < MIN_REQUEST_INTERVAL:
            logger.warning(f"Rate limit hit. Only {time_since_last} seconds since last request")
            return jsonify({
                'error': {
                    'message': f'Please wait {MIN_REQUEST_INTERVAL} seconds between requests',
                    'type': 'rate_limit',
                }
            }), 429
            
        last_request_time = current_time
        
        # Extract the message
        data = request.get_json()
        logger.info(f"Request data: {data}")
        
        messages = data['messages']
        last_message = messages[-1]
        prompt = last_message['content']
        request_id = str(int(time.time()))
        
        logger.info(f"Processing request {request_id} with prompt: {prompt}")
        
        # Handle the Claude interaction
        response = handle_claude_interaction(prompt)
        logger.info(f"Got response for request {request_id}: {response}")
        
        return jsonify({
            'id': f'chatcmpl-{request_id}',
            'object': 'chat.completion',
            'created': int(time.time()),
            'model': 'gpt-3.5-turbo-0613',
            'choices': [{
                'index': 0,
                'message': {
                    'role': 'assistant',
                    'content': response
                },
                'finish_reason': 'stop'
            }],
            'usage': {
                'prompt_tokens': 1,
                'completion_tokens': 1,
                'total_tokens': 2
            }
        })
    
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return jsonify({
            'error': {
                'message': str(e),
                'type': 'server_error',
                'param': None,
                'code': None
            }
        }), 500

if __name__ == '__main__':
    logger.info("Starting Claude API Bridge server on port 3000")
    app.run(port=3000)
