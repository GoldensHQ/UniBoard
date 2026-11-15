# -*- coding: utf-8 -*-
"""Мини-процесс перехвата клавиатуры/мыши UniBoard.

Запускается главным приложением. Единственная задача — глобальные LL-хуки.
Колбэк хука содержит только целочисленные сравнения и запись события в
кольцевой буфер mmap: никаких системных вызовов, которые могут зависнуть,
никакой расшифровки раскладки, никакого ожидания главного процесса.

Главный процесс умер/завис? Перехватчик через ~4 секунды без heartbeat
сам снимает хуки и завершается — ввод системы никогда не остаётся «в плену».
"""
import ctypes
import os
import struct
import sys
import time
from ctypes import wintypes

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core import hookproto as P          # noqa: E402
from core import kbd, winapi             # noqa: E402

user32 = winapi.user32

WM_TIMER = 0x0113
_MOUSE_DOWN = (0x0201, 0x0204, 0x0207, 0x020B, 0x020C)
_VK_ESC, _VK_UP, _VK_DOWN, _VK_TAB, _VK_RETURN = 0x1B, 0x26, 0x28, 0x09, 0x0D


def run(mmap_path):
    mm, f = P.map_file(mmap_path)
    # ждём, пока главный процесс проставит MAGIC (мгновение)
    for _ in range(100):
        if P.read_u32(mm, P.OFF_MAGIC) == P.MAGIC:
            break
        time.sleep(0.05)
    else:
        return

    unpack = struct.unpack_from
    pack_into = struct.pack_into
    state = {"mods": 0, "last_hb": 0, "miss": 0}

    def push(kind, vk, scan, bits):
        try:
            wi = unpack("<I", mm, P.OFF_WIDX)[0]
            pack_into("<IIII", mm, P.record_offset(wi), kind, vk, scan, bits)
            pack_into("<I", mm, P.OFF_WIDX, wi + 1)
        except Exception:
            pass

    def kb_cb(ncode, wp, lp):
        try:
            if ncode == 0:
                info = ctypes.cast(lp, ctypes.POINTER(kbd.KBDLLHOOKSTRUCT)).contents
                if not info.flags & kbd.LLKHF_INJECTED:
                    vk = info.vkCode
                    down = wp == kbd.WM_KEYDOWN or wp == kbd.WM_SYSKEYDOWN
                    m = state["mods"]
                    if vk == kbd.VK_CAPITAL:
                        if down:
                            m ^= P.MOD_CAPS
                    elif vk in (kbd.VK_SHIFT, kbd.VK_LSHIFT, kbd.VK_RSHIFT):
                        m = (m | P.MOD_SHIFT) if down else (m & ~P.MOD_SHIFT)
                    elif vk in (kbd.VK_CONTROL, kbd.VK_LCONTROL, kbd.VK_RCONTROL):
                        m = (m | P.MOD_CTRL) if down else (m & ~P.MOD_CTRL)
                    elif vk in (kbd.VK_MENU, kbd.VK_LMENU, kbd.VK_RMENU):
                        m = (m | P.MOD_ALT) if down else (m & ~P.MOD_ALT)
                    elif vk in (kbd.VK_LWIN, kbd.VK_RWIN):
                        m = (m | P.MOD_WIN) if down else (m & ~P.MOD_WIN)
                    state["mods"] = m
                    bits = m | (P.MOD_DOWN if down else 0)
                    block = False
                    if down:
                        flags = unpack("<I", mm, P.OFF_FLAGS)[0]
                        mods = m & 0x0F
                        hk0 = unpack("<II", mm, P.OFF_HK)
                        hk1 = unpack("<II", mm, P.OFF_HK + 8)
                        if (hk0[0] and hk0[0] == vk and hk0[1] == mods) or \
                           (hk1[0] and hk1[0] == vk and hk1[1] == mods):
                            block = True
                        elif flags & P.FLAG_POPUP:
                            if vk in (_VK_ESC, _VK_UP, _VK_DOWN):
                                block = True
                            elif vk == _VK_TAB and flags & P.FLAG_TAB and flags & P.FLAG_CANDS:
                                block = True
                            elif vk == _VK_RETURN and flags & P.FLAG_ENTER and flags & P.FLAG_CANDS:
                                block = True
                    push(0, vk, info.scanCode, bits)
                    if block:
                        return 1  # поглотить
        except Exception:
            pass
        return user32.CallNextHookEx(None, ncode, wp, lp)

    def mouse_cb(ncode, wp, lp):
        try:
            if ncode == 0 and wp in _MOUSE_DOWN:
                info = ctypes.cast(lp, ctypes.POINTER(kbd.MSLLHOOKSTRUCT)).contents
                if not info.flags & kbd.LLKHF_INJECTED:
                    x = ctypes.c_int32(info.pt.x).value & 0xFFFFFFFF
                    y = ctypes.c_int32(info.pt.y).value & 0xFFFFFFFF
                    push(1, wp, x, y)
        except Exception:
            pass
        return user32.CallNextHookEx(None, ncode, wp, lp)

    kb_proc = kbd.HOOKPROC(kb_cb)
    ms_proc = kbd.HOOKPROC(mouse_cb)
    hmod = winapi.kernel32.GetModuleHandleW(None)
    kb_hook = user32.SetWindowsHookExW(kbd.WH_KEYBOARD_LL, kb_proc, hmod, 0)
    ms_hook = user32.SetWindowsHookExW(kbd.WH_MOUSE_LL, ms_proc, hmod, 0)
    if not kb_hook:
        P.write_u32(mm, P.OFF_STATUS, 2)
        return
    P.write_u32(mm, P.OFF_STATUS, 1)

    user32.SetTimer(None, 0, 400, None)
    msg = wintypes.MSG()
    while True:
        r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if r <= 0:
            break
        if msg.message == WM_TIMER:
            try:
                if P.read_u32(mm, P.OFF_SHUTDOWN) == 0xFFFFFFFF:
                    break
                hb = P.read_u32(mm, P.OFF_HEARTBEAT)
                if hb != state["last_hb"]:
                    state["last_hb"] = hb
                    state["miss"] = 0
                else:
                    state["miss"] += 1
                    if state["miss"] > 10:  # ~4 с тишины — главный процесс умер
                        break
            except Exception:
                pass
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

    if kb_hook:
        user32.UnhookWindowsHookEx(kb_hook)
    if ms_hook:
        user32.UnhookWindowsHookEx(ms_hook)
    user32.KillTimer(None, 0)
    try:
        mm.close()
        f.close()
    except Exception:
        pass


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        run(sys.argv[1])
