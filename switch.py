import keyboard
import pyperclip
import time
import tkinter as tk
from tkinter import messagebox
import threading
import pystray
from PIL import Image, ImageDraw
import os
import shutil
import sys
import win32com.client


# initialize tkinter
root = tk.Tk()
root.title("Switch")
root.iconbitmap("switch.ico")
messagebox.showinfo(
    "Switch",
    "البرنامج شغال في الخلفية\n\n"
    "علشان تحول النص العربي لنص إنجليزي أو العكس:\n"
    "١. حدد النص وخده نسخ باستخدام (Ctrl + C)\n"
    "٢. شغّل التطبيق بالاختصار (Ctrl + L)"
)

# set the keyboard mapping
keyboard_map = {
    # Lowercase
    'a': 'ش', 'b': 'لا', 'c': 'ؤ', 'd': 'ي', 'e': 'ث', 'f': 'ب', 'g': 'ل', 'h': 'ا',
    'i': 'ه', 'j': 'ت', 'k': 'ن', 'l': 'م', 'm': 'ة', 'n': 'ى', 'o': 'خ', 'p': 'ح',
    'q': 'ض', 'r': 'ق', 's': 'س', 't': 'ف', 'u': 'ع', 'v': 'ر', 'w': 'ص', 'x': 'ء',
    'y': 'غ', 'z': 'ئ',

    # Uppercase (Shift + letter)
    'A': 'ِ', 'B': 'لآ', 'C': 'ْ', 'D': 'ُ', 'E': 'إ', 'F': 'ب', 'G': 'لأ', 'H': 'أ',
    'I': '÷', 'J': 'ـ', 'K': '،', 'L': '/', 'M': '’', 'N': 'آ', 'O': '×', 'P': '؛',
    'Q': 'َ', 'R': 'ً', 'S': 'ٍ', 'T': 'ٌ', 'U': 'ْ', 'V': 'ز', 'W': 'ً', 'X': 'ْ',
    'Y': 'إ', 'Z': 'ْ', ':':'ك',';':'ك',"'": 'ط','"': 'ط',
}



# add shortcut to startup

def add_to_startup():
    startup_path = os.path.join(os.getenv('APPDATA'), 'Microsoft\\Windows\\Start Menu\\Programs\\Startup')
    file_path = sys.argv[0] 
    shortcut_path = os.path.join(startup_path, "Switch.lnk")

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(shortcut_path)
    shortcut.TargetPath = file_path
    shortcut.WorkingDirectory = os.path.dirname(file_path)
    shortcut.IconLocation = file_path
    shortcut.save()

add_to_startup()

# when user press ctrl+l to run the application
def on_hotkey():
    keyboard.press_and_release('ctrl+c')
    time.sleep(0.1) 
    text = pyperclip.paste()
    convert(text)    
    
# initialize run application hot key
keyboard.add_hotkey('ctrl+l', on_hotkey)

# convert letters to arabic 
def convert(text):
    arabic_to_english_map = {v: k for k, v in keyboard_map.items()}
    
    if not text:
        return

    first_char = text[0]

    # check if the first char is arabic or english
    if '\u0600' <= first_char <= '\u06FF':
        converted = ''.join(arabic_to_english_map.get(c, c) for c in text)    
    else:
        converted = ''.join(keyboard_map.get(c, c) for c in text)

    do_copy(converted)

# copy and paste the arabic word, then show to the user
def do_copy(text):        
    pyperclip.copy(text)
    time.sleep(0.3) 
    keyboard.press_and_release('ctrl+v')

def on_quit(icon, item):
    icon.stop()
    root.quit()

def setup_tray():
    icon = pystray.Icon("Switch", Image.open("switch_icon.jpg"), "Switch - محول النص")
    icon.menu = pystray.Menu(
        pystray.MenuItem("Quit", on_quit)
    )
    icon.run()

# Run tray in separate thread so it doesn't block
threading.Thread(target=setup_tray, daemon=True).start()

# run the application without gui
root.withdraw()
root.mainloop()

