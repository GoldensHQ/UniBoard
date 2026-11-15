"""UniBoard configuration: paths, defaults, hotkeys, autostart."""
import json
import os
import tempfile
from pathlib import Path

APP_NAME = "UniBoard"


def app_dir() -> Path:
    """Application data directory: %APPDATA%\\UniBoard."""
    base = os.getenv("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_PATH = app_dir() / "config.json"
SNIPPETS_PATH = app_dir() / "snippets.json"
HISTORY_PATH = app_dir() / "history.json"
IMAGES_DIR = app_dir() / "images"
LOG_PATH = app_dir() / "uniboard.log"

DEFAULTS = {
    # Suggestions while typing
    "suggest_enabled": True,       # suggestions in general
    "suggest_min_chars": 3,        # minimum typed characters before showing
    "suggest_max_items": 6,        # maximum rows in the suggestion popup
    "suggest_snippets": True,      # offer snippets
    "suggest_special": True,       # offer links, e-mails, colors, JSON
    "suggest_plain_text": False,   # offer plain texts (from 24 characters)
    "snippet_auto": False,         # auto-expand a snippet on exact trigger match
    "popup_timeout_ms": 10000,     # suggestion popup auto-hide, ms
    # Insertion
    "insert_mode": "unicode",      # "unicode" — type char by char; "clipboard" — via clipboard
    "restore_clipboard": True,     # restore the previous clipboard after pasting
    # History
    "hotkey_accept": "Ctrl+Space",     # insert the suggestion (Tab is off-limits without hooks)
    "hotkey_history": "Ctrl+Alt+V",    # history window
    "hotkey_paste_last": "Ctrl+Alt+X", # paste the newest item
    "history_size": 500,               # how many items to keep
    "record_enabled": True,            # record the clipboard
    "watch_interval_ms": 400,          # clipboard polling interval, ms
    # Misc
    "excluded_apps": ["keepass", "1password", "bitwarden", "enpass"],  # no suggestions here
    "autostart": False,            # start together with Windows
}

# --- Hotkeys ----------------------------------------------------------------

_VK_NAMES = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B,
    "escape": 0x1B, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "insert": 0x2D, "ins": 0x2D, "home": 0x24, "end": 0x23,
    "pgup": 0x21, "pageup": 0x21, "pgdn": 0x22, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "comma": 0xBC, "period": 0xBE, "slash": 0xBF, "minus": 0xBD, "plus": 0xBB,
}
_MOD_ALIASES = {"ctrl": "ctrl", "control": "ctrl", "ctl": "ctrl",
                "alt": "alt", "menu": "alt",
                "shift": "shift", "win": "win", "super": "win", "meta": "win"}


class Hotkey:
    """A parsed hotkey: set of modifiers + virtual key."""

    __slots__ = ("name", "mods", "vk", "raw")

    def __init__(self, name, mods, vk, raw):
        self.name = name
        self.mods = frozenset(mods)
        self.vk = vk
        self.raw = raw

    def matches(self, ev):
        return ev.down and ev.vk == self.vk and ev.mods == self.mods

    @staticmethod
    def parse(raw, name):
        """'Ctrl+Alt+V' -> Hotkey | None."""
        if not raw:
            return None
        mods, vk = set(), None
        for tok in str(raw).split("+"):
            t = tok.strip().lower()
            if not t:
                continue
            if t in _MOD_ALIASES:
                mods.add(_MOD_ALIASES[t])
                continue
            if t.startswith("f") and t[1:].isdigit():
                n = int(t[1:])
                if 1 <= n <= 24:
                    vk = 0x70 + n - 1
                    continue
            if len(t) == 1:
                ch = t.upper()
                if ch.isdigit() or ("A" <= ch <= "Z"):
                    vk = ord(ch)
                    continue
                vk = _VK_NAMES.get(t)
                if vk:
                    continue
            if t in _VK_NAMES:
                vk = _VK_NAMES[t]
        if vk is None or not mods:
            return None
        return Hotkey(name, mods, vk, raw)


def load_hotkeys(cfg):
    """Build the list of active hotkeys from the config."""
    out = []
    hk = Hotkey.parse(cfg.get("hotkey_accept"), "accept")
    if hk:
        out.append(hk)
    hk = Hotkey.parse(cfg.get("hotkey_history"), "history")
    if hk:
        out.append(hk)
    hk = Hotkey.parse(cfg.get("hotkey_paste_last"), "paste_last")
    if hk:
        out.append(hk)
    return out


# --- Autostart via the registry ----------------------------------------------

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_autostart(enable: bool) -> bool:
    try:
        import winreg
        exe = Path(__file__).resolve().parent.parent / "uniboard.pyw"
        import sys
        py = Path(sys.executable)
        if py.name.lower() == "python.exe":
            py = py.with_name("pythonw.exe")
        val = f'"{py}" "{exe}"'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            if enable:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, val)
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


def autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except Exception:
        return False


# --- Config -------------------------------------------------------------------

class Config:
    """A simple dict-backed config with JSON load/save."""

    def __init__(self, path: Path = CONFIG_PATH):
        self.path = Path(path)
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            if self.path.exists():
                with open(self.path, encoding="utf-8") as f:
                    stored = json.load(f)
                if isinstance(stored, dict):
                    self.data.update(stored)
        except Exception:
            pass  # corrupted config — fall back to defaults

    def get(self, key, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self.data[key] = value

    def update(self, new: dict):
        for k, v in new.items():
            self.data[k] = v

    def save(self):
        try:
            self._atomic_write(self.path, json.dumps(self.data, ensure_ascii=False, indent=2))
        except Exception:
            pass

    @staticmethod
    def _atomic_write(path: Path, text: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
