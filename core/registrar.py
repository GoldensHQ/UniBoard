# -*- coding: utf-8 -*-
"""Hotkeys without low-level hooks.

RegisterHotKey is an official OS API: the system itself invokes our handler,
there is no global keyboard interception. All UniBoard actions (inserting a
suggestion, history, "paste the last item") go through this mechanism.
"""
import ctypes
import logging
import threading
from ctypes import wintypes

from . import winapi

log = logging.getLogger("uniboard")

user32 = winapi.user32
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_APP_RELOAD = 0x8001
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 1, 2, 4, 8
MOD_MAP = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "shift": MOD_SHIFT, "win": MOD_WIN}
FIRST_ID = 2000
MAX_SLOTS = 8


class HotkeyRegistrar:
    """Registers hotkeys on its own thread (hwnd=None → WM_HOTKEY
    arrives in the thread's message queue)."""

    def __init__(self, app):
        self.app = app
        self._thread = None
        self._tid = 0
        self._ids = {}

    def start(self):
        self._thread = threading.Thread(target=self._run,
                                        name="UniBoard-Hotkeys", daemon=True)
        self._thread.start()

    def stop(self):
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)

    def reload(self):
        """Re-register the keys (after settings change)."""
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_APP_RELOAD, 0, 0)

    def _register(self, hotkeys):
        for hid in list(self._ids):
            user32.UnregisterHotKey(None, hid)
        self._ids = {}
        for i, hk in enumerate(hotkeys[:MAX_SLOTS]):
            mods = 0
            for name, bit in MOD_MAP.items():
                if name in hk.mods:
                    mods |= bit
            if user32.RegisterHotKey(None, FIRST_ID + i, mods, hk.vk):
                self._ids[FIRST_ID + i] = hk.name
            else:
                log.warning("RegisterHotKey rejected %s (possibly already taken "
                            "by another program)", hk.raw)
        if not self._ids and hotkeys:
            log.error("No hotkey was registered")

    def _run(self):
        self._tid = winapi.kernel32.GetCurrentThreadId()
        self._register(self.app.hotkeys)
        msg = wintypes.MSG()
        while True:
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r <= 0:
                break
            if msg.message == WM_HOTKEY:
                name = self._ids.get(msg.wParam)
                if name:
                    self.app.worker_q.put(("hotkey", name))
            elif msg.message == WM_APP_RELOAD:
                self._register(self.app.hotkeys)
        for hid in list(self._ids):
            user32.UnregisterHotKey(None, hid)
        self._ids = {}
