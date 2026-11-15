"""Конфигурация UniBoard: пути, значения по умолчанию, горячие клавиши, автозапуск."""
import json
import os
import tempfile
from pathlib import Path

APP_NAME = "UniBoard"


def app_dir() -> Path:
    """Каталог данных приложения: %APPDATA%\\UniBoard."""
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
    # Подсказки при печати
    "suggest_enabled": True,       # общие подсказки (Tab)
    "suggest_min_chars": 3,        # с какого числа символов показывать
    "suggest_max_items": 6,        # максимум вариантов в окне подсказки
    "suggest_snippets": True,      # предлагать сниппеты
    "suggest_special": True,       # предлагать ссылки, e-mail, цвета, JSON
    "suggest_plain_text": False,   # предлагать обычные тексты (от 24 символов)
    "snippet_auto": False,         # авто-разворачивание сниппета при точном совпадении
    "popup_timeout_ms": 10000,     # автоскрытие окна подсказки, мс
    # Вставка
    "insert_mode": "unicode",      # "unicode" — печатать посимвольно; "clipboard" — через буфер
    "restore_clipboard": True,     # возвращать прежний буфер после вставки
    # История
    "hotkey_accept": "Ctrl+Space",     # вставить подсказку (Tab нельзя без хука)
    "hotkey_history": "Ctrl+Alt+V",    # окно истории
    "hotkey_paste_last": "Ctrl+Alt+X", # вставить последний элемент
    "history_size": 500,               # сколько элементов хранить
    "record_enabled": True,            # запись буфера обмена
    "watch_interval_ms": 400,          # интервал опроса буфера, мс
    # Прочее
    "excluded_apps": ["keepass", "1password", "bitwarden", "enpass"],  # не показывать подсказки
    "autostart": False,            # запуск вместе с Windows
}

# --- Горячие клавиши -------------------------------------------------------

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
    """Разобранная горячая клавиша: набор модификаторов + виртуальная клавиша."""

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
    """Собрать список активных горячих клавиш из конфига."""
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


# --- Автозапуск через реестр ------------------------------------------------

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


# --- Конфиг ----------------------------------------------------------------

class Config:
    """Простой dict-конфиг с загрузкой/сохранением в JSON."""

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
            pass  # повреждённый конфиг — используем значения по умолчанию

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
