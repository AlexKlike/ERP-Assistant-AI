import pyautogui
import winsound
import time
from config import ANCHOR_PATH

def is_window_open():
    try:
        if pyautogui.locateOnScreen(ANCHOR_PATH, confidence=0.7):
            return True
    except:
        pass
    return False

def alarm():
    winsound.Beep(1000, 800)
