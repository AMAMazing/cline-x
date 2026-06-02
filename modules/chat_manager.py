import time

chat_history = []
MAX_CHAT_HISTORY = 50

def add_chat_message(role, text, full_text=None):
    message = {'role': role, 'text': text, 'time': time.strftime('%H:%M')}
    if full_text:
        message['full_text'] = full_text
    chat_history.append(message)
    if len(chat_history) > MAX_CHAT_HISTORY:
        chat_history.pop(0)