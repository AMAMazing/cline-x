import time
import pyautogui
from optimisewait import optimiseWait
from modules.clipboard_utils import set_clipboard

def process_optimisewait_message(message, debug: bool = False):
    optimiseWait('newchat', autopath='linkimages')
    optimiseWait('taskhere', autopath='linkimages')
    
    set_clipboard(message, debug=debug)
    time.sleep(0.1)
    
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.1) 
    pyautogui.press('enter')