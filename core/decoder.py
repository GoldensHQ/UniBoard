"""Расшифровка клавиш в символы раскладки — ВНЕ потока низкоуровневого хука.

Вызов ToUnicode/ToAscii из колбэка WH_KEYBOARD_LL — известная причина
общесистемного зависания ввода: если активное окно не отвечает, хук-колбэк
виснет вместе со всей клавиатурой. Поэтому:
  * хук крадёт клавиши мгновенно и решает только «поглотить/пропустить»;
  * символ для буфера набора расшифровывает этот отдельный поток;
  * если ToUnicodeEx не ответил за таймаут — декодер помечается «умершим»
    и подсказки отключаются, но система и UniBoard продолжают работать.
"""
import ctypes
from ctypes import wintypes
import logging
import queue
import threading

from . import kbd, winapi

log = logging.getLogger("uniboard")

user32 = winapi.user32

user32.ToUnicodeEx.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                               ctypes.c_wchar_p, ctypes.c_int, wintypes.UINT,
                               ctypes.c_size_t]
user32.ToUnicodeEx.restype = ctypes.c_int
user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
user32.GetKeyboardLayout.restype = ctypes.c_size_t

DECODE_TIMEOUT = 0.12  # сек: сколько ждём ответа декодера


def _decode(vk, scan, mods, caps):
    """Виртуальная клавиша -> символ раскладки (ToUnicodeEx), иначе None."""
    if vk in kbd.MODIFIER_VKS or vk in kbd.CLEAR_VKS or 0x70 <= vk <= 0x87:
        return None
    if "win" in mods:
        return None
    if ("ctrl" in mods) != ("alt" in mods):
        return None  # шорткаты (Ctrl+C, Alt+…) — это не печатание
    state = (wintypes.BYTE * 256)()
    if "shift" in mods:
        state[kbd.VK_SHIFT] = state[kbd.VK_LSHIFT] = 0x80
    if "ctrl" in mods:
        state[kbd.VK_CONTROL] = state[kbd.VK_LCONTROL] = 0x80
    if "alt" in mods:
        state[kbd.VK_MENU] = state[kbd.VK_LMENU] = 0x80
    if caps:
        state[kbd.VK_CAPITAL] = 1
    # раскладка берётся у потока активного окна (раскладки могут быть разные)
    fg = winapi.fg_hwnd()
    tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    hkl = user32.GetKeyboardLayout(tid) if tid else user32.GetKeyboardLayout(0)
    buf = ctypes.create_unicode_buffer(8)
    r = user32.ToUnicodeEx(vk, scan, state, buf, 8, 0, hkl)
    if r == 1:
        c = buf[0]
        if c.isprintable():
            return c
    return None


class CharDecoder(threading.Thread):
    """Однозадачный поток-расшифровщик с таймаутом и аварийным отключением."""

    def __init__(self):
        super().__init__(name="UniBoard-Decoder", daemon=True)
        self.q = queue.Queue()
        self.done = threading.Event()
        self.result = None
        self.dead = False

    def run(self):
        while True:
            job = self.q.get()
            if job is None:
                return
            try:
                self.result = _decode(*job)
            except Exception:
                self.result = None
            self.done.set()

    def decode(self, vk, scan, mods, caps):
        """Символ для буфера набора; None — если декодер умер или символа нет."""
        if self.dead:
            return None
        self.done.clear()
        self.q.put((vk, scan, frozenset(mods), caps))
        if not self.done.wait(DECODE_TIMEOUT):
            self.dead = True
            log.error("Декодер раскладки не ответил за %.2f с — подсказки "
                      "отключены до перезапуска UniBoard (система не пострадала).",
                      DECODE_TIMEOUT)
            return None
        return self.result

    def stop(self):
        try:
            self.q.put(None)
        except Exception:
            pass
