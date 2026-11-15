"""Клавиатура: эмуляция ввода (SendInput), дожитие отпускания комбинаций."""
import ctypes
from ctypes import wintypes
import threading
import time

from . import winapi

user32 = winapi.user32

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
LLKHF_INJECTED = 0x10
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
WM_QUIT = 0x0012

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_CAPITAL = 0x14
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_INSERT = 0x2D
VK_DELETE = 0x2E
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_APPS = 0x5D
VK_NUMLOCK = 0x90
VK_SCROLL = 0x91
VK_LSHIFT, VK_RSHIFT = 0xA0, 0xA1
VK_LCONTROL, VK_RCONTROL = 0xA2, 0xA3
VK_LMENU, VK_RMENU = 0xA4, 0xA5

VK_LBUTTON, VK_RBUTTON, VK_MBUTTON = 0x01, 0x02, 0x04
VK_XBUTTON1, VK_XBUTTON2 = 0x06, 0x07

# Клавиши, сбрасывающие буфер набора
CLEAR_VKS = frozenset({VK_TAB, VK_RETURN, VK_ESCAPE, VK_SPACE, VK_END, VK_HOME,
                       VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN, VK_INSERT, VK_DELETE,
                       VK_LWIN, VK_RWIN, VK_APPS})
MODIFIER_VKS = frozenset({VK_SHIFT, VK_LSHIFT, VK_RSHIFT, VK_CONTROL,
                          VK_LCONTROL, VK_RCONTROL, VK_MENU, VK_LMENU,
                          VK_RMENU, VK_LWIN, VK_RWIN, VK_CAPITAL,
                          VK_NUMLOCK, VK_SCROLL, VK_APPS})

_MOD_GROUPS = {
    "shift": (VK_SHIFT, VK_LSHIFT, VK_RSHIFT),
    "ctrl": (VK_CONTROL, VK_LCONTROL, VK_RCONTROL),
    "alt": (VK_MENU, VK_LMENU, VK_RMENU),
    "win": (VK_LWIN, VK_RWIN),
}


def mods_now():
    """Текущие зажатые модификаторы (по GetAsyncKeyState)."""
    mods = set()
    for name, vks in _MOD_GROUPS.items():
        for vk in vks:
            if user32.GetAsyncKeyState(vk) & 0x8000:
                mods.add(name)
                break
    return frozenset(mods)


class KeyEv:
    __slots__ = ("vk", "scan", "down", "injected", "mods", "caps")

    def __init__(self, vk, scan, down, injected, mods, caps):
        self.vk = vk
        self.scan = scan
        self.down = down
        self.injected = injected
        self.mods = mods
        self.caps = caps


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", winapi.POINT), ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int,
                              wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.restype = ctypes.c_size_t
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_size_t, wintypes.DWORD]
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_size_t]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [ctypes.c_size_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
winapi.kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
winapi.kernel32.GetModuleHandleW.restype = ctypes.c_size_t
winapi.kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.SendInput.restype = wintypes.UINT
user32.GetAsyncKeyState.restype = ctypes.c_short


# --- структуры INPUT --------------------------------------------------------

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]


# --- События клавиатуры: перехват -------------------------------------------

class KeyboardHook:
    """Глобальный LL-хук клавиатуры. on_key(ev)->True означает «поглотить клавишу»."""

    def __init__(self, on_key, on_error=None):
        self._on_key = on_key
        self._on_error = on_error
        self._hook = None
        self._tid = 0
        self._thread = None
        self._proc = HOOKPROC(self._cb)
        self._caps = False  # трекаем CapsLock сами (состояние потока-хука недоступно)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="UniBoard-KbdHook", daemon=True)
        self._thread.start()

    def stop(self):
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)
        self._hook = None

    def _run(self):
        self._tid = winapi.kernel32.GetCurrentThreadId()
        hmod = winapi.kernel32.GetModuleHandleW(None)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, hmod, 0)
        if not self._hook:
            err = ctypes.get_last_error()
            if self._on_error:
                self._on_error("Не удалось установить перехват клавиатуры "
                               f"(SetWindowsHookExW, ошибка {err})")
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(self._hook)

    def _cb(self, ncode, wparam, lparam):
        # МАКСИМАЛЬНО тощий колбэк: никакой расшифровки символов здесь нет.
        # ToUnicode/ToAscii внутри LL-хука может заморозить ввод всей системы,
        # поэтому символы раскладки расшифрует отдельный поток (core/decoder.py).
        try:
            if ncode == 0:
                info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not info.flags & LLKHF_INJECTED:  # свои инъекции пропускаем
                    down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                    if down and info.vkCode == VK_CAPITAL:
                        self._caps = not self._caps
                    ev = KeyEv(info.vkCode, info.scanCode, bool(down), False,
                               mods_now(), self._caps)
                    if self._on_key(ev):
                        return 1  # поглотить
        except Exception:
            pass
        return user32.CallNextHookEx(None, ncode, wparam, lparam)


class MouseHook:
    """LL-хук мыши: уведомляет о нажатиях кнопок (всегда пропускает событие дальше)."""

    WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN = 0x0201, 0x0204, 0x0207
    _BTN = {0x0201: "left", 0x0204: "right", 0x0207: "middle",
            0x020B: "x1", 0x020C: "x2"}

    def __init__(self, on_click):
        self._on_click = on_click
        self._hook = None
        self._tid = 0
        self._thread = None
        self._proc = HOOKPROC(self._cb)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="UniBoard-MouseHook", daemon=True)
        self._thread.start()

    def stop(self):
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)
        self._hook = None

    def _run(self):
        self._tid = winapi.kernel32.GetCurrentThreadId()
        hmod = winapi.kernel32.GetModuleHandleW(None)
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, hmod, 0)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)

    def _cb(self, ncode, wparam, lparam):
        try:
            if ncode == 0 and wparam in self._BTN:
                info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if not info.flags & LLKHF_INJECTED:
                    self._on_click(info.pt.x, info.pt.y)
        except Exception:
            pass
        return user32.CallNextHookEx(None, ncode, wparam, lparam)


# --- Ввод: эмуляция нажатий --------------------------------------------------

def _ki(vk, scan, flags):
    i = INPUT()
    i.type = INPUT_KEYBOARD
    i.ki.wVk = vk
    i.ki.wScan = scan
    i.ki.dwFlags = flags
    return i


def _send(events, chunk=250):
    arr = (INPUT * len(events))(*events)
    sent = 0
    off = 0
    size = ctypes.sizeof(INPUT)
    while off < len(events):
        n = min(chunk, len(events) - off)
        ptr = ctypes.cast(ctypes.byref(arr, off * size), ctypes.POINTER(INPUT))
        got = user32.SendInput(n, ptr, size)
        if got != n:
            import logging
            logging.getLogger("uniboard").warning(
                "SendInput: отправлено %d из %d (GetLastError=%s)",
                got, n, ctypes.get_last_error())
        sent += got
        off += n
        if off < len(events):
            threading.Event().wait(0.002)
    return sent


def tap_key(vk, scan=0):
    """Нажать и отпустить клавишу."""
    _send([_ki(vk, scan, 0), _ki(vk, scan, KEYEVENTF_KEYUP)])


def send_backspaces(n):
    """Отправить n Backspace (удалить набранный триггер в целевом приложении)."""
    if n <= 0:
        return
    evs = []
    for _ in range(min(n, 256)):
        evs.append(_ki(VK_BACK, 0x0E, 0))
        evs.append(_ki(VK_BACK, 0x0E, KEYEVENTF_KEYUP))
    _send(evs)


_MOD_RELEASE_VKS = (VK_CONTROL, VK_LCONTROL, VK_RCONTROL,
                    VK_MENU, VK_LMENU, VK_RMENU,
                    VK_SHIFT, VK_LSHIFT, VK_RSHIFT,
                    VK_LWIN, VK_RWIN)
_MOD_REPRESS_VKS = (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN)


def release_modifiers():
    """«Отпустить» зажатые модификаторы инъекцией KEYUP.

    Критично после срабатывания RegisterHotKey: пока пользователь держит
    Ctrl+Space (или Ctrl+Alt+X), система считает Ctrl зажатым, и весь
    инъектируемый текст доходит до приложения как Ctrl+символ — то есть
    как шорткаты, а не как печать (наблюдение на реальной системе).
    """
    evs = [_ki(vk, 0, KEYEVENTF_KEYUP) for vk in _MOD_RELEASE_VKS
           if user32.GetAsyncKeyState(vk) & 0x8000]
    if evs:
        _send(evs)


def wait_modifiers_released(timeout=0.7):
    """Дождаться, пока пользователь физически отпустит модификаторы и клавишу
    горячей комбинации. RegisterHotKey срабатывает, пока клавиши ещё зажаты;
    инъекция в этот момент может теряться/искажаться в некоторых приложениях,
    поэтому перед вставкой лучше дождаться отпускания (как делает espanso)."""
    end = time.time() + timeout
    while time.time() < end:
        held = any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in _MOD_REPRESS_VKS)
        held = held or user32.GetAsyncKeyState(VK_SPACE) & 0x8000
        if not held:
            return True
        time.sleep(0.01)
    return False


def restore_modifiers():
    """Вернуть модификаторы, которые пользователь всё ещё держит физически,
    чтобы его следующие сочетания (Ctrl+C и т.п.) работали как обычно."""
    evs = [_ki(vk, 0, 0) for vk in _MOD_REPRESS_VKS
           if user32.GetAsyncKeyState(vk) & 0x8000]
    if evs:
        _send(evs)


def type_text(text):
    """Напечатать текст событиями UNICODE (работает в любой раскладке)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    evs = []
    for ch in text:
        if ch == "\n":
            evs.append(_ki(VK_RETURN, 0x1C, 0))
            evs.append(_ki(VK_RETURN, 0x1C, KEYEVENTF_KEYUP))
        else:
            b = ch.encode("utf-16-le")
            for i in range(0, len(b), 2):
                unit = b[i] | (b[i + 1] << 8)
                evs.append(_ki(0, unit, KEYEVENTF_UNICODE))
                evs.append(_ki(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    _send(evs)


def press_ctrl_v():
    """Ctrl+V — вставка из буфера обмена."""
    _send([_ki(VK_CONTROL, 0x1D, 0)])
    threading.Event().wait(0.02)
    _send([_ki(ord("V"), 0x2F, 0), _ki(ord("V"), 0x2F, KEYEVENTF_KEYUP)])
    threading.Event().wait(0.02)
    _send([_ki(VK_CONTROL, 0x1D, KEYEVENTF_KEYUP)])
