import json
import os
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import keyboard
import pyperclip
import pystray
from PIL import Image


APP_DIR = Path(os.getenv("APPDATA", Path.home())) / "Switch"
SETTINGS_FILE = APP_DIR / "settings.json"
STARTUP_LINK = Path(os.getenv("APPDATA", APP_DIR)) / "Microsoft/Windows/Start Menu/Programs/Startup/Switch.lnk"


def resource_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


# Windows Arabic (101) keyboard layout.
ENGLISH_TO_ARABIC = {
    "q": "ض", "w": "ص", "e": "ث", "r": "ق", "t": "ف", "y": "غ",
    "u": "ع", "i": "ه", "o": "خ", "p": "ح", "[": "ج", "]": "د",
    "a": "ش", "s": "س", "d": "ي", "f": "ب", "g": "ل", "h": "ا",
    "j": "ت", "k": "ن", "l": "م", ";": "ك", "'": "ط", "z": "ئ",
    "x": "ء", "c": "ؤ", "v": "ر", "b": "لا", "n": "ى", "m": "ة",
    ",": "و", ".": "ز", "/": "ظ", "Q": "َ", "W": "ً", "E": "ُ",
    "R": "ٌ", "T": "لإ", "Y": "إ", "U": "‘", "I": "÷", "O": "×",
    "P": "؛", "{": "<", "}": ">", "A": "ِ", "S": "ٍ", "D": "]",
    "F": "[", "G": "لأ", "H": "أ", "J": "ـ", "K": "،", "L": "/",
    ":": ":", '"': '"', "Z": "~", "X": "ْ", "C": "}", "V": "{",
    "B": "لآ", "N": "آ", "M": "’", "<": ",", ">": ".", "?": "؟",
}

DEFAULTS = {
    "convert_hotkey": "ctrl+l",
    "auto_select_line": True,
    "start_with_windows": False,
    "show_on_start": True,
}


def load_settings():
    settings = DEFAULTS.copy()
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        settings.update({key: value for key, value in saved.items() if key in DEFAULTS})
    except (OSError, ValueError, TypeError):
        pass
    return settings


def save_settings(settings):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def text_starts_arabic(text):
    for char in text:
        if "\u0600" <= char <= "\u06ff":
            return True
        if char.isascii() and char.isalpha():
            return False
    return False


def convert_layout(text):
    """Convert text typed with the wrong Arabic/English keyboard layout."""
    if not text:
        return text
    if text_starts_arabic(text):
        reverse_map = {}
        for english, arabic in ENGLISH_TO_ARABIC.items():
            reverse_map.setdefault(arabic, english)
        # Convert character-by-character so common words such as "السلام" are
        # not mistaken for the optional two-character Lam-Alef key mapping.
        return "".join(reverse_map.get(char, char) for char in text)
    # Caps Lock or Shift should not change the intended Arabic letters.
    # Treat Latin A-Z exactly like their lowercase physical keys.
    return "".join(
        ENGLISH_TO_ARABIC.get(char.lower(), char)
        if char.isascii() and char.isalpha()
        else ENGLISH_TO_ARABIC.get(char, char)
        for char in text
    )


class HotkeyRecorder:
    MODIFIERS = {
        "ctrl", "left ctrl", "right ctrl", "alt", "left alt", "right alt",
        "shift", "left shift", "right shift", "windows", "left windows", "right windows",
    }
    NORMALIZED = {
        "left ctrl": "ctrl", "right ctrl": "ctrl", "left alt": "alt", "right alt": "alt",
        "left shift": "shift", "right shift": "shift", "left windows": "windows",
        "right windows": "windows",
    }
    # Physical set-1 scan codes for the main keyboard area. Using these avoids
    # recording an Arabic glyph, uppercase letter, or symbol produced by Shift.
    PHYSICAL_KEYS = {
        1: "esc", 2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6",
        8: "7", 9: "8", 10: "9", 11: "0", 12: "-", 13: "=",
        14: "backspace", 15: "tab", 16: "q", 17: "w", 18: "e", 19: "r",
        20: "t", 21: "y", 22: "u", 23: "i", 24: "o", 25: "p",
        26: "[", 27: "]", 28: "enter", 30: "a", 31: "s", 32: "d",
        33: "f", 34: "g", 35: "h", 36: "j", 37: "k", 38: "l",
        39: ";", 40: "'", 41: "`", 43: "\\", 44: "z", 45: "x",
        46: "c", 47: "v", 48: "b", 49: "n", 50: "m", 51: ",",
        52: ".", 53: "/", 57: "space", 59: "f1", 60: "f2", 61: "f3",
        62: "f4", 63: "f5", 64: "f6", 65: "f7", 66: "f8", 67: "f9",
        68: "f10", 87: "f11", 88: "f12",
    }

    def __init__(self, root, on_status):
        self.root, self.on_status = root, on_status
        self.on_complete = lambda value: None
        self.hook, self.pressed, self.candidate = None, [], []

    def start(self):
        self.cancel(False)
        self.pressed, self.candidate = [], []
        self.on_status("اضغط الاختصار الآن…  (Esc للإلغاء)")
        self.hook = keyboard.hook(self._event, suppress=False)

    def _event(self, event):
        raw_name = (event.name or "").lower()
        name = self.NORMALIZED.get(raw_name, raw_name)
        if name not in self.MODIFIERS:
            name = self.PHYSICAL_KEYS.get(event.scan_code, name)
        if event.event_type == keyboard.KEY_DOWN:
            if name == "esc":
                self.root.after(0, self.cancel)
                return
            if name and name not in self.pressed:
                self.pressed.append(name)
            if name and name not in self.MODIFIERS:
                self.candidate = self.pressed.copy()
        elif event.event_type == keyboard.KEY_UP:
            if name not in self.MODIFIERS and self.candidate:
                combo = "+".join(self.candidate)
                self.root.after(0, lambda value=combo: self.finish(value))
            if name in self.pressed:
                self.pressed.remove(name)

    def finish(self, combo):
        self.cancel(False)
        self.on_complete(combo)
        self.on_status(f"تم التعرف على: {combo}")

    def cancel(self, show_status=True):
        if self.hook is not None:
            try:
                keyboard.unhook(self.hook)
            except (KeyError, ValueError):
                pass
            self.hook = None
        if show_status:
            self.on_status("جاهز")


class SwitchApp:
    BG, CARD, TEXT, MUTED = "#F5F7FB", "#FFFFFF", "#172033", "#697386"
    BLUE, BLUE_DARK = "#3B6DF6", "#2F58C9"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Switch — محول الكتابة")
        self.root.geometry("650x540")
        self.root.minsize(590, 500)
        self.root.configure(bg=self.BG)
        try:
            self.root.iconbitmap(resource_path("switch.ico"))
        except tk.TclError:
            pass
        self.settings = load_settings()
        self.convert_hotkey = tk.StringVar(value=self.settings["convert_hotkey"])
        self.auto_select_line = tk.BooleanVar(value=self.settings["auto_select_line"])
        self.start_with_windows = tk.BooleanVar(value=self.settings["start_with_windows"])
        self.show_on_start = tk.BooleanVar(value=self.settings["show_on_start"])
        self.status = tk.StringVar(value="جاهز")
        self.registered_hotkeys, self.tray_icon = [], None
        self.current_hotkey_keys = []
        self.action_lock = threading.Lock()
        self.recorder = HotkeyRecorder(self.root, self.status.set)
        self._configure_styles()
        self._build_ui()
        self._register_hotkeys(True)
        self._sync_startup(False)
        self._start_tray()
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        if not self.settings.get("show_on_start", True):
            self.root.withdraw()

    def _configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=self.BG)
        style.configure("Card.TFrame", background=self.CARD)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.CARD, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI Semibold", 22))
        style.configure("Subtitle.TLabel", background=self.BG, foreground=self.MUTED, font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=self.CARD, foreground=self.TEXT, font=("Segoe UI Semibold", 12))
        style.configure("Hint.TLabel", background=self.CARD, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure("Accent.TButton", background=self.BLUE, foreground="white", padding=(18, 9), borderwidth=0, font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton", background=[("active", self.BLUE_DARK)])
        style.configure("TButton", padding=(12, 8), font=("Segoe UI", 9))
        style.configure("TRadiobutton", background=self.CARD, foreground=self.TEXT, font=("Segoe UI", 9))
        style.configure("TCheckbutton", background=self.CARD, foreground=self.TEXT, font=("Segoe UI", 9))

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=(28, 22))
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Switch", style="Title.TLabel").pack(anchor="e")
        ttk.Label(outer, text="صحّح الكتابة المكتوبة بلغة كيبورد غير مقصودة من أي برنامج", style="Subtitle.TLabel").pack(anchor="e", pady=(2, 18))

        shortcuts = ttk.Frame(outer, style="Card.TFrame", padding=20)
        shortcuts.pack(fill="x", pady=(0, 12))
        ttk.Label(shortcuts, text="اختصارات الكيبورد", style="Section.TLabel").pack(anchor="e")
        ttk.Label(shortcuts, text="اضغط «تسجيل» ثم نفّذ الاختصار على كيبوردك؛ البرنامج سيتعرف على الأزرار تلقائيًا.", style="Hint.TLabel", wraplength=540, justify="right").pack(anchor="e", pady=(4, 14))
        self._hotkey_row(shortcuts, "تحويل عربي ⇄ إنجليزي", self.convert_hotkey)
        ttk.Checkbutton(
            shortcuts,
            text="لو مفيش نص متحدد، حوّل تلقائيًا من بداية السطر لمكان المؤشر",
            variable=self.auto_select_line,
        ).pack(anchor="e", pady=(10, 0))

        options = ttk.Frame(outer, style="Card.TFrame", padding=20)
        options.pack(fill="x", pady=(0, 12))
        ttk.Label(options, text="خيارات التشغيل", style="Section.TLabel").pack(anchor="e", pady=(0, 8))
        ttk.Checkbutton(options, text="تشغيل Switch مع بداية ويندوز", variable=self.start_with_windows).pack(anchor="e", pady=3)
        ttk.Checkbutton(options, text="إظهار النافذة عند تشغيل التطبيق", variable=self.show_on_start).pack(anchor="e", pady=3)

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(3, 0))
        ttk.Label(footer, textvariable=self.status, style="Subtitle.TLabel").pack(side="left", padx=(4, 0))
        ttk.Button(footer, text="حفظ الإعدادات", style="Accent.TButton", command=self.save).pack(side="right")
        ttk.Label(outer, text="اكتب النص واضغط الاختصار مباشرة، أو حدد جزءًا معينًا لتحويله وحده.", style="Subtitle.TLabel").pack(anchor="e", pady=(16, 0))

    def _hotkey_row(self, parent, label, variable):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", pady=5)
        ttk.Button(row, text="تسجيل", command=lambda: self._record_hotkey(variable)).pack(side="left")
        ttk.Entry(row, textvariable=variable, width=23, justify="center", state="readonly").pack(side="left", padx=8)
        ttk.Label(row, text=label, style="Card.TLabel").pack(side="right")

    def _record_hotkey(self, variable):
        self._remove_hotkeys()
        def complete(combo):
            variable.set(combo)
            self._register_hotkeys(False)
        self.recorder.on_complete = complete
        self.recorder.start()

    def _remove_hotkeys(self):
        for hotkey_id in self.registered_hotkeys:
            try:
                keyboard.remove_hotkey(hotkey_id)
            except (KeyError, ValueError):
                pass
        self.registered_hotkeys.clear()

    def _register_hotkeys(self, show_error=False):
        self._remove_hotkeys()
        try:
            convert = self.convert_hotkey.get().strip().lower()
            if not convert:
                raise ValueError("لا يمكن ترك الاختصار فارغًا")
            self.current_hotkey_keys = [key.strip() for key in convert.split("+") if key.strip()]
            self.registered_hotkeys.append(keyboard.add_hotkey(convert, self._run_action))
            return True
        except Exception as exc:
            self._remove_hotkeys()
            self.status.set(f"تعذر تسجيل الاختصار: {exc}")
            if show_error:
                messagebox.showerror("خطأ في الاختصار", str(exc), parent=self.root)
            return False

    def _run_action(self):
        threading.Thread(target=self._process_selection, daemon=True).start()

    def _process_selection(self):
        # A hotkey can fire when its final character is released while Alt,
        # Shift, or Ctrl is still physically down. Wait before generating our
        # own Ctrl+C/Ctrl+V so the two chords cannot merge into an OS/OEM action.
        deadline = time.monotonic() + 5.0
        keys_to_release = self.current_hotkey_keys or ["ctrl", "alt", "shift"]
        while time.monotonic() < deadline:
            if not any(keyboard.is_pressed(key) for key in keys_to_release):
                break
            time.sleep(0.02)
        else:
            self.root.after(0, lambda: self.status.set("ارفع أزرار الاختصار ثم جرّب مرة أخرى"))
            return

        if not self.action_lock.acquire(blocking=False):
            return
        old_clipboard = None
        try:
            try:
                old_clipboard = pyperclip.paste()
            except pyperclip.PyperclipException:
                pass
            sentinel = f"__SWITCH_{time.time_ns()}__"
            pyperclip.copy(sentinel)
            keyboard.press_and_release("ctrl+c")
            time.sleep(0.18)
            selected = pyperclip.paste()
            if (not selected or selected == sentinel) and self.settings.get("auto_select_line", True):
                # With no explicit selection, transform everything before the caret
                # on the current line. This makes the common typo-fix a single hotkey.
                keyboard.press_and_release("shift+home")
                time.sleep(0.08)
                pyperclip.copy(sentinel)
                keyboard.press_and_release("ctrl+c")
                time.sleep(0.18)
                selected = pyperclip.paste()
            if not selected or selected == sentinel:
                self.root.after(0, lambda: self.status.set("مفيش نص قبل المؤشر علشان يتحول"))
                return
            result = convert_layout(selected)
            pyperclip.copy(result)
            keyboard.press_and_release("ctrl+v")
            time.sleep(0.25)
            self.root.after(0, lambda: self.status.set("تم بنجاح"))
        except Exception as exc:
            self.root.after(0, lambda error=exc: self.status.set(f"حدث خطأ: {error}"))
        finally:
            if old_clipboard is not None:
                try:
                    pyperclip.copy(old_clipboard)
                except pyperclip.PyperclipException:
                    pass
            self.action_lock.release()

    def _sync_startup(self, show_error=True):
        try:
            if self.start_with_windows.get():
                import win32com.client
                STARTUP_LINK.parent.mkdir(parents=True, exist_ok=True)
                shortcut = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(STARTUP_LINK))
                if getattr(sys, "frozen", False):
                    shortcut.TargetPath, shortcut.Arguments = sys.executable, ""
                else:
                    pythonw = Path(sys.executable).with_name("pythonw.exe")
                    shortcut.TargetPath = str(pythonw if pythonw.exists() else sys.executable)
                    shortcut.Arguments = f'"{Path(__file__).resolve()}"'
                shortcut.WorkingDirectory = str(Path(__file__).resolve().parent)
                shortcut.IconLocation = str(resource_path("switch.ico"))
                shortcut.save()
            elif STARTUP_LINK.exists():
                STARTUP_LINK.unlink()
            return True
        except Exception as exc:
            if show_error:
                messagebox.showerror("التشغيل مع ويندوز", f"تعذر تحديث الإعداد:\n{exc}", parent=self.root)
            return False

    def save(self):
        if not self._register_hotkeys(True) or not self._sync_startup(True):
            return
        self.settings.update({
            "convert_hotkey": self.convert_hotkey.get(),
            "start_with_windows": self.start_with_windows.get(),
            "show_on_start": self.show_on_start.get(), "auto_select_line": self.auto_select_line.get(),
        })
        try:
            save_settings(self.settings)
            self.status.set("تم حفظ الإعدادات")
        except OSError as exc:
            messagebox.showerror("حفظ الإعدادات", f"تعذر الحفظ:\n{exc}", parent=self.root)

    def show_window(self, icon=None, item=None):
        self.root.after(0, self._show_window)

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_window(self):
        self.recorder.cancel()
        self.root.withdraw()
        self.status.set("التطبيق يعمل بجوار الساعة")

    def _start_tray(self):
        try:
            menu = pystray.Menu(pystray.MenuItem("فتح الإعدادات", self.show_window, default=True), pystray.MenuItem("خروج", self.quit))
            self.tray_icon = pystray.Icon("Switch", Image.open(resource_path("switch_icon.jpg")), "Switch — محول الكتابة", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as exc:
            self.status.set(f"تعذر تشغيل أيقونة شريط المهام: {exc}")

    def quit(self, icon=None, item=None):
        self.recorder.cancel(False)
        self._remove_hotkeys()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self.root.destroy)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    SwitchApp().run()
