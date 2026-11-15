"""Minimal WinAPI wrappers: caret, windows, monitors, processes."""
import ctypes
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GA_ROOT = 2
MONITOR_DEFAULTTONEAREST = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
                ("rcCaret", RECT)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]


# restype/argtypes (important for x64 — otherwise pointers are truncated)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
user32.GetGUIThreadInfo.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.MonitorFromPoint.argtypes = [POINT, wintypes.DWORD]
user32.MonitorFromPoint.restype = ctypes.c_size_t
user32.GetMonitorInfoW.argtypes = [ctypes.c_size_t, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def fg_hwnd():
    return user32.GetForegroundWindow()


def fg_process_name():
    """Lowercase .exe name of the active window's process, e.g. 'chrome.exe'."""
    hwnd = fg_hwnd()
    if not hwnd:
        return ""
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name.lower()
    finally:
        kernel32.CloseHandle(h)
    return ""


def caret_screen_pos():
    """Screen position of the text caret; fallback — the mouse position."""
    gti = GUITHREADINFO()
    gti.cbSize = ctypes.sizeof(GUITHREADINFO)
    if user32.GetGUIThreadInfo(0, ctypes.byref(gti)) and gti.hwndCaret:
        pt = POINT(gti.rcCaret.left, gti.rcCaret.bottom)
        if user32.ClientToScreen(gti.hwndCaret, ctypes.byref(pt)):
            return int(pt.x), int(pt.y)
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y) + 20


def cursor_pos():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def workarea_at(x, y):
    """Work area of the monitor (without the taskbar) containing the point."""
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    hmon = user32.MonitorFromPoint(POINT(int(x), int(y)), MONITOR_DEFAULTTONEAREST)
    if hmon and user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        r = mi.rcWork
        return int(r.left), int(r.top), int(r.right), int(r.bottom)
    return 0, 0, 1920, 1040


def window_center(hwnd):
    if not hwnd:
        return None
    r = RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return (r.left + r.right) // 2, (r.top + r.bottom) // 2
    return None


def tk_root_hwnd(widget):
    """The real HWND of the tkinter window (a Toplevel wrapper)."""
    try:
        return user32.GetAncestor(widget.winfo_id(), GA_ROOT)
    except Exception:
        return None


def set_noactivate(widget):
    """WS_EX_NOACTIVATE: clicks on the window do not move focus to it —
    the suggestion does not "steal" the active window when its rows are clicked."""
    hwnd = tk_root_hwnd(widget)
    if not hwnd:
        return False
    try:
        style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) or 0
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE,
                                 style | WS_EX_NOACTIVATE | WS_EX_TOPMOST)
        return True
    except Exception:
        return False
