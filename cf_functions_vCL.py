from time import sleep
import webbrowser
import pyautogui
import win32clipboard
import subprocess
from datetime import timedelta
from random import randint
import os
import shutil

def delete_if_exists(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"Deleted existing file: {file_path}")

def deleteall(processing):
    # Deleted everything from processing folder
    for filename in os.listdir(processing):
        file_path = os.path.join(processing, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                fd = os.open(file_path, os.O_RDWR)
                os.close(fd)
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

def optimiseWait(filename, waitnot=False, specreg=None, click=True, xoff=0, yoff=0, doubleclick=False, tripleclick=False, autopath=r'D:\BobaDays\Auto', orfile=None, orclick=False, orthree=None, orthreeclick=False):
    clicked = 0
    while True:
        if specreg is None:
            findloc = pyautogui.locateCenterOnScreen(fr'{autopath}\{filename}.png', confidence=0.9)
            if findloc:
                clicked = 1
            if orfile is not None and not findloc:
                findloc = pyautogui.locateCenterOnScreen(fr'{autopath}\{orfile}.png', confidence=0.9)
                if findloc and clicked == 0:
                    clicked = 2
                if orthree is not None and not findloc:
                    findloc = pyautogui.locateCenterOnScreen(fr'{autopath}\{orthree}.png', confidence=0.9)
                    if findloc and clicked == 0:
                        clicked = 3
        else:
            findloc = pyautogui.locateOnScreen(fr'{autopath}\{filename}.png', region=specreg, confidence=0.9)
            if orfile is not None:
                findloc = pyautogui.locateCenterOnScreen(fr'{autopath}\{orfile}.png', confidence=0.9)
                if orthree is not None:
                    findloc = pyautogui.locateCenterOnScreen(fr'{autopath}\{orthree}.png', confidence=0.9)
            clicked = 1

        if waitnot is False:
            if findloc:
                break # If the image was found and clicked, exit the loop.
            if doubleclick is True:
                pyautogui.doubleClick()
            if tripleclick is True:
                pyautogui.tripleClick()
        else:
            if not findloc:
                print('waitnot: image not found')
                break # If the image was not found, exit the loop.
            else:
                print('waitnot: image found')
                break
        sleep(1) # Pause for half a second to prevent CPU overuse.
    if click is True and clicked == 1:
        if findloc is not None:
            if specreg is None:
                x, y = findloc
            else:
                x, y, width, height = findloc
            xmod = x + xoff
            ymod = y + yoff
            sleep(1)
            pyautogui.click(xmod, ymod)
            print('clicked')
    if orclick is True and clicked == 2:
        if findloc is not None:
            if specreg is None:
                x, y = findloc
            else:
                x, y, width, height = findloc
            xmod = x + xoff
            ymod = y + yoff
            sleep(0.5)
            pyautogui.click(xmod, ymod)

    if orthreeclick is True and clicked == 3:
        if findloc is not None:
            if specreg is None:
                x, y = findloc
            else:
                x, y, width, height = findloc
            xmod = x + xoff
            ymod = y + yoff
            sleep(0.5)
            pyautogui.click(xmod, ymod)


def cmd(command, wait=False):
    command = f'cmd /c "{command}"'
    process = subprocess.Popen(command, shell=True)
    if wait is True:
        process.wait()

def upload_youtube(filepath, title, description=None, channelurl='https://studio.youtube.com/channel/UCCXAXV5NRHxTdHvym1MF1kg', thumbnail=None):
    webbrowser.open(channelurl)

    optimiseWait('create')
    optimiseWait('uploadvids')
    optimiseWait('select')
    optimiseWait('filename', click=False)
    pyautogui.typewrite(filepath)
    pyautogui.press('enter')
    optimiseWait('title', yoff=10,click=False)
    pyautogui.hotkey('ctrl','a')

    pyautogui.typewrite(title)
    if description:
        if thumbnail == None:
            sleep(3)
        optimiseWait('tell')
        pyautogui.typewrite(description)
    if thumbnail:
        optimiseWait('thumbnail')
        optimiseWait('filename', click=False)
        pyautogui.typewrite(thumbnail)
        pyautogui.press('enter')

    for i in range(0,7):
        optimiseWait('next', waitnot=True)
    optimiseWait('public')
    optimiseWait('publish')
    optimiseWait('process', click=False, orfile="published", orclick=False)
    pyautogui.hotkey('ctrl', 'w')

def upload_tiktok(filepath, title, hashtags=None):
    url = 'https://www.tiktok.com/upload?lang=en'

    webbrowser.open(url)

    optimiseWait('slctfile')
    sleep(0.1)
    optimiseWait('filename', click=False)
    pyautogui.typewrite(filepath)
    pyautogui.press('enter')
    optimiseWait('caption', yoff=25)

    pyautogui.typewrite(title)
    if hashtags:
        pyautogui.press('space')
        sleep(0.5)
        for hashtag in hashtags:
            pyautogui.typewrite('#' + hashtag)
            sleep(1.5)
            pyautogui.press('space')

    optimiseWait('edit', click=False, orfile='notnow',orclick=True,orthree='whiteedit') #stuck
    pyautogui.scroll(-600) 
    sleep(0.1)
    optimiseWait('post')
    optimiseWait('uploads2', click=False)
    pyautogui.hotkey('ctrl', 'w')
    optimiseWait('leave')

def upload_insta(filepath, title):
    webbrowser.open("https://www.instagram.com/")

    optimiseWait('instacreate')
    optimiseWait('instaselect')
    optimiseWait('filename', click=False)
    pyautogui.typewrite(filepath)
    pyautogui.press('enter')
    optimiseWait('thingy')
    optimiseWait('916')
    optimiseWait('instanext')
    sleep(1)
    optimiseWait('instanext2')
    optimiseWait('instacap')
    pyautogui.typewrite(title)
    optimiseWait('instashare')
    optimiseWait('instashared', click=False)
    pyautogui.hotkey('ctrl', 'w')

def upload_three(filepath, title):
    upload_youtube(filepath,title)
    upload_tiktok(filepath,title)
    upload_insta(filepath,title)