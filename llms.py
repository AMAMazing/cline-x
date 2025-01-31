from time import sleep
import webbrowser
import win32clipboard
from optimisewait import optimiseWait, set_autopath
import pyautogui
import time
import pywintypes

def set_clipboard(text, retries=3, delay=0.2):
    for i in range(retries):
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            try:
                win32clipboard.SetClipboardText(str(text))
            except Exception:
                # Fallback for Unicode characters
                win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, str(text).encode('utf-16le'))
            win32clipboard.CloseClipboard()
            return  # Success
        except pywintypes.error as e:
            if e.winerror == 5:  # Access is denied
                print(f"Clipboard access denied. Retrying... (Attempt {i+1}/{retries})")
                time.sleep(delay)
            else:
                raise  # Re-raise other pywintypes errors
        except Exception as e:
            raise  # Re-raise other exceptions
    print(f"Failed to set clipboard after {retries} attempts.")

def talkto(llm, prompt):
    llm = llm.lower()

    set_autopath(rf'D:\cline-x-claudeweb\images\{llm}')
    urls = {
        'deepseek': 'https://chat.deepseek.com/',
        'gemini': 'https://aistudio.google.com/prompts/new_chat',
        'chatgpt':'https://chatgpt.com/?model=o1'
    }

    webbrowser.open_new_tab(urls[llm])

    optimiseWait('message')

    set_clipboard(prompt)   
    pyautogui.hotkey('ctrl','v')

    sleep(1)

    optimiseWait('run')
    
    if llm == 'gemini':
        optimiseWait('done',clicks=0)

    optimiseWait('copy')    
    
    pyautogui.hotkey('ctrl','w')
    
    pyautogui.hotkey('alt','tab')

    # Get Claude's response
    win32clipboard.OpenClipboard()
    response = win32clipboard.GetClipboardData()
    win32clipboard.CloseClipboard()

    return response


if __name__ == "__main__":
    print(talkto('deepseek','Hi'))