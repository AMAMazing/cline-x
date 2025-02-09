from time import sleep
import webbrowser
import win32clipboard
from optimisewait import optimiseWait, set_autopath
import pyautogui
import time
import pywintypes
import base64
import io
from PIL import Image

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

def talkto(llm, prompt, imagedata=None, chatgpt='o1'):
    llm = llm.lower()

    set_autopath(rf'D:\cline-x-claudeweb\images\{llm}')
    urls = {
        'deepseek': 'https://chat.deepseek.com/',
        'gemini': 'https://aistudio.google.com/prompts/new_chat',
        'chatgpt': f'https://chatgpt.com/?model={chatgpt}'
    }

    webbrowser.open_new_tab(urls[llm])

    if llm == 'chatgpt':
        optimiseWait('loaded',clicks=0)

    optimiseWait('message',clicks=2)

    # If there are images, paste each one
    if imagedata:
        for img in imagedata:
            set_clipboard_image(img)
            pyautogui.hotkey('ctrl', 'v')
            sleep(7)  # Ensure upload completes before pasting the next image

    set_clipboard(prompt)
    pyautogui.hotkey('ctrl', 'v')

    sleep(1)

    optimiseWait('run')
    
    if llm == 'gemini':
        optimiseWait('done')

    if llm != 'chatgpt':
        optimiseWait('copy')
    else:
        while (optimiseWait('copy',dontwait=True)['found']) == False:
            optimiseWait('down',dontwait=True)
        optimiseWait('copy')
    
    pyautogui.hotkey('ctrl', 'w')
    
    pyautogui.hotkey('alt', 'tab')

    # Get LLM's response
    win32clipboard.OpenClipboard()
    response = win32clipboard.GetClipboardData()
    win32clipboard.CloseClipboard()

    return response

def set_clipboard_image(image_data, retries=3, delay=0.2):
    """Set image data to clipboard with retries"""
    for attempt in range(retries):
        try:
            binary_data = base64.b64decode(image_data.split(',')[1])
            image = Image.open(io.BytesIO(binary_data))

            output = io.BytesIO()
            image.convert("RGB").save(output, "BMP")
            data = output.getvalue()[14:]  # Remove bitmap header
            output.close()

            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            win32clipboard.CloseClipboard()
            return True
        except pywintypes.error as e:
            if e.winerror == 5:  # Access is denied
                print(f"Clipboard access denied. Retrying... (Attempt {attempt+1}/{retries})")
                time.sleep(delay)
            else:
                raise  # Re-raise other pywintypes errors
        except Exception as e:
            print(f"Error setting image to clipboard: {e}")
            return False
    return False


if __name__ == "__main__":
    print(talkto('gemini','How to easily get element names and such for selenium or other headless webbrowser automation',chatgpt='o3-mini-high'))