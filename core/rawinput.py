# -*- coding: utf-8 -*-
"""Keyboard listener via Raw Input (WM_INPUT) — WITHOUT low-level hooks.

Why this is safe for the system: Raw Input DELIVERS events to our hidden
window asynchronously (by posting to the message queue). The system input
thread waits nothing from us — unlike WH_KEYBOARD_LL, where the whole
system's input synchronously waits for the callback. If our thread slows
down/hangs, only our handler suffers; the keyboard and mouse keep working
as usual.

Events cannot be "swallowed" (a fundamental difference from a hook), so
suggestion insertion is done via a hotkey (Ctrl+Space by default).
"""
import ctypes
from ctypes import wintypes
import threading

from . import winapi

user32 = winapi.user32
kernel32 = winapi.kernel32

WM_INPUT = 0x00FF
WM_QUIT = 0x0012
RIM_TYPEKEYBOARD = 1
RID_INPUT = 0x10000003
RIDEV_INPUTSINK = 0x00000100  # exactly 0x100! (0x1 is RIDEV_REMOVE)
RI_KEY_BREAK = 0x01
# IMPORTANT: Raw Input is not delivered to message-only windows — a regular
# hidden top-level window is needed (we never show it).
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("usMakeCode", wintypes.USHORT), ("usFlags", wintypes.USHORT),
                ("usReserved", wintypes.USHORT), ("usVKey", wintypes.USHORT),
                ("uMsg", wintypes.UINT), ("ulExtraInformation", wintypes.ULONG)]


user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR,
                                   wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT,
                                   ctypes.c_void_p,
                                   ctypes.POINTER(wintypes.UINT), wintypes.UINT]
user32.GetRawInputData.restype = wintypes.UINT
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE),
                                           wintypes.UINT, wintypes.UINT]
user32.RegisterRawInputDevices.restype = wintypes.BOOL


class RawInputListener(threading.Thread):
    """Hidden window + RegisterRawInputDevices(keyboard, INPUTSINK).

    on_key(ev) is called on this same thread (a lightweight queueing).
    Modifiers and CapsLock are tracked incrementally.
    """

    def __init__(self, on_key, on_error=None):
        super().__init__(name="UniBoard-RawInput", daemon=True)
        self._on_key = on_key
        self._on_error = on_error
        self._tid = 0
        self._hwnd = None
        self._mods = 0
        self._caps = False
        self._wndproc = WNDPROC(self._proc)
        self._buf = (ctypes.c_ubyte * 256)()

    def start(self):
        super().start()

    def stop(self):
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)

    # --- window and registration ------------------------------------------------------

    def run(self):
        self._tid = kernel32.GetCurrentThreadId()
        hinstance = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.lpszClassName = "UniBoardRawInput"
        wc.hInstance = hinstance
        if not user32.RegisterClassW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err != 1410:  # 1410 = CLASS_ALREADY_EXISTS — we can continue
                if self._on_error:
                    self._on_error(f"RegisterClassW: error {err}")
                return
        self._hwnd = user32.CreateWindowExW(
            WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE, "UniBoardRawInput",
            "UniBoardRawInput", 0, 0, 0, 0, 0,
            None, None, hinstance, None)
        if not self._hwnd:
            if self._on_error:
                self._on_error(f"CreateWindowExW: error {ctypes.get_last_error()}")
            return
        rid = RAWINPUTDEVICE(1, 6, RIDEV_INPUTSINK, self._hwnd)  # keyboard
        if not user32.RegisterRawInputDevices(ctypes.byref(rid), 1,
                                              ctypes.sizeof(RAWINPUTDEVICE)):
            if self._on_error:
                self._on_error(f"RegisterRawInputDevices: "
                               f"error {ctypes.get_last_error()}")
            return
        msg = wintypes.MSG()
        while True:
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._hwnd:
            user32.DestroyWindow(self._hwnd)

    # --- events ------------------------------------------------------------------

    def _proc(self, hwnd, msg, wp, lp):
        try:
            if msg == WM_INPUT:
                self._handle_wm_input(lp)
        except Exception:
            pass
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    def _handle_wm_input(self, lparam):
        size = wintypes.UINT(ctypes.sizeof(self._buf))
        n = user32.GetRawInputData(lparam, RID_INPUT, self._buf,
                                   ctypes.byref(size),
                                   ctypes.sizeof(RAWINPUTHEADER))
        if n <= 0:
            return
        hdr = RAWINPUTHEADER.from_buffer(self._buf)
        if hdr.dwType != RIM_TYPEKEYBOARD:
            return
        kb = RAWKEYBOARD.from_buffer(self._buf, ctypes.sizeof(RAWINPUTHEADER))
        vk = kb.usVKey
        if not vk or vk > 0xFF:
            return
        down = not (kb.usFlags & RI_KEY_BREAK)
        if down and vk == 0x14:  # VK_CAPITAL
            self._caps = not self._caps
        m = self._mods
        from . import kbd
        if vk in (kbd.VK_SHIFT, kbd.VK_LSHIFT, kbd.VK_RSHIFT):
            m = (m | 1) if down else (m & ~1)
        elif vk in (kbd.VK_CONTROL, kbd.VK_LCONTROL, kbd.VK_RCONTROL):
            m = (m | 2) if down else (m & ~2)
        elif vk in (kbd.VK_MENU, kbd.VK_LMENU, kbd.VK_RMENU):
            m = (m | 4) if down else (m & ~4)
        elif vk in (kbd.VK_LWIN, kbd.VK_RWIN):
            m = (m | 8) if down else (m & ~8)
        self._mods = m
        mods = _bits_to_mods(m)
        ev = kbd.KeyEv(vk, kb.usMakeCode, bool(down), False, mods,
                       bool(self._caps))
        self._on_key(ev)


def _bits_to_mods(bits):
    names = []
    if bits & 1:
        names.append("shift")
    if bits & 2:
        names.append("ctrl")
    if bits & 4:
        names.append("alt")
    if bits & 8:
        names.append("win")
    return frozenset(names)
