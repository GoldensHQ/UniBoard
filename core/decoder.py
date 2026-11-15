"""Decoding keys into layout characters — OUTSIDE the low-level hook thread.

Calling ToUnicode/ToAscii from a WH_KEYBOARD_LL callback is a well-known
cause of system-wide input freeze: if the active window stops responding,
the hook callback hangs along with the entire keyboard. Therefore:
  * the hook steals keys instantly and only decides "swallow or pass";
  * the character for the type buffer is decoded by this separate thread;
  * if ToUnicodeEx does not answer within the timeout, the decoder is marked
    "dead" and suggestions are disabled, but the system and UniBoard keep working.
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

DECODE_TIMEOUT = 0.12  # sec: how long we wait for the decoder's answer


def _decode(vk, scan, mods, caps):
    """Virtual key -> keyboard layout character (ToUnicodeEx), otherwise None."""
    if vk in kbd.MODIFIER_VKS or vk in kbd.CLEAR_VKS or 0x70 <= vk <= 0x87:
        return None
    if "win" in mods:
        return None
    if ("ctrl" in mods) != ("alt" in mods):
        return None  # shortcuts (Ctrl+C, Alt+…) are not typing
    state = (wintypes.BYTE * 256)()
    if "shift" in mods:
        state[kbd.VK_SHIFT] = state[kbd.VK_LSHIFT] = 0x80
    if "ctrl" in mods:
        state[kbd.VK_CONTROL] = state[kbd.VK_LCONTROL] = 0x80
    if "alt" in mods:
        state[kbd.VK_MENU] = state[kbd.VK_LMENU] = 0x80
    if caps:
        state[kbd.VK_CAPITAL] = 1
    # the layout is taken from the active window's thread (layouts may differ)
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
    """Single-purpose decoder thread with a timeout and emergency shutdown."""

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
        """Character for the type buffer; None — if the decoder is dead or there is no character."""
        if self.dead:
            return None
        self.done.clear()
        self.q.put((vk, scan, frozenset(mods), caps))
        if not self.done.wait(DECODE_TIMEOUT):
            self.dead = True
            log.error("The layout decoder did not respond within %.2f s — suggestions "
                      "are disabled until UniBoard is restarted (the system was not affected).",
                      DECODE_TIMEOUT)
            return None
        return self.result

    def stop(self):
        try:
            self.q.put(None)
        except Exception:
            pass
