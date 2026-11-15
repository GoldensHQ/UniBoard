"""История буфера обмена, сниппеты и умный подбор подсказок."""
import json
import re
import threading
import time
import uuid
from pathlib import Path

from . import config as cfgmod
from .theme import trunc

LINK_RE = re.compile(r"^(https?://\S+|www\.\S+)$", re.IGNORECASE)
EMAIL_RE = re.compile(r"^[\w.+\-]+@[\w\-]+\.[\w.\-]+$")
COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

MAX_TEXT_LEN = 100_000


def classify(text: str) -> str:
    """Определить тип содержимого: link / email / color / json / text."""
    s = (text or "").strip()
    if not s:
        return "text"
    if s[0] in "{[":
        try:
            json.loads(s)
            return "json"
        except Exception:
            pass
    if "\n" not in s and "\r" not in s:
        if LINK_RE.match(s):
            return "link"
        if EMAIL_RE.match(s):
            return "email"
        if COLOR_RE.match(s):
            return "color"
    return "text"


ICON_BY_TYPE = {"link": "🔗", "email": "✉", "color": "🎨", "json": "{}",
                "text": "📋", "image": "🖼", "files": "📁"}


class ClipboardItem:
    __slots__ = ("id", "type", "text", "paths", "image", "created", "uses", "pinned")

    def __init__(self, type_, text=None, paths=None, image=None, created=None,
                 uses=0, pinned=False, id_=None):
        self.id = id_ or uuid.uuid4().hex[:12]
        self.type = type_
        self.text = text
        self.paths = paths
        self.image = image
        self.created = created if created is not None else time.time()
        self.uses = uses or 0
        self.pinned = bool(pinned)

    # --- содержимое ---------------------------------------------------------

    @property
    def content_key(self):
        if self.type == "files":
            return ("files", tuple(self.paths or ()))
        if self.type == "image":
            return ("image", self.image or "")
        return ("text", self.text or "")

    @property
    def icon(self):
        return ICON_BY_TYPE.get(self.type, "📋")

    def preview(self, n=70):
        if self.type == "files":
            names = [Path(p).name for p in (self.paths or [])]
            return trunc("%d файл(ов): %s" % (len(names), ", ".join(names)), n)
        if self.type == "image":
            return "Изображение (PNG)"
        return trunc(self.text or "", n)

    def to_dict(self):
        return {"id": self.id, "type": self.type, "text": self.text,
                "paths": self.paths, "image": self.image, "created": self.created,
                "uses": self.uses, "pinned": self.pinned}

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("type", "text"), text=d.get("text"), paths=d.get("paths"),
                   image=d.get("image"), created=d.get("created", 0),
                   uses=d.get("uses", 0), pinned=d.get("pinned", False),
                   id_=d.get("id"))


class Candidate:
    """Вариант подсказки: что печатать, как показать и на что сослаться."""

    __slots__ = ("insert", "display", "icon", "ref", "score")

    def __init__(self, insert, display, icon, ref, score):
        self.insert = insert
        self.display = display
        self.icon = icon
        self.ref = ref
        self.score = score


class History:
    """Список элементов (новые в начале) с потокобезопасным доступом."""

    def __init__(self, path: Path = cfgmod.HISTORY_PATH, capacity: int = 500):
        self.path = Path(path)
        self.capacity = capacity
        self.items = []
        self.dirty = False
        self._lock = threading.RLock()
        self.load()

    def load(self):
        try:
            if self.path.exists():
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                self.items = [ClipboardItem.from_dict(d) for d in data]
        except Exception:
            self.items = []

    def save(self):
        with self._lock:
            items = [i.to_dict() for i in self.items]
        try:
            cfgmod.Config._atomic_write(self.path, json.dumps(items, ensure_ascii=False))
            self.dirty = False
        except Exception:
            pass

    def maybe_save(self, min_interval=3.0):
        now = time.time()
        if self.dirty and now - getattr(self, "_last_save", 0) > min_interval:
            self._last_save = now
            self.save()

    # --- операции ------------------------------------------------------------

    def add(self, item: ClipboardItem):
        """Добавить копию; дубликат не плодим — поднимаем наверх."""
        with self._lock:
            key = item.content_key
            for i, old in enumerate(self.items):
                if old.content_key == key:
                    old.created = item.created
                    self.items.pop(i)
                    self.items.insert(0, old)
                    self._prune_locked()
                    self.dirty = True
                    return old
            self.items.insert(0, item)
            self._prune_locked()
            self.dirty = True
            return item

    def _prune_locked(self):
        cap = max(10, self.capacity)
        if len(self.items) <= cap:
            return
        kept = [it for it in self.items if it.pinned]
        rest = [it for it in self.items if not it.pinned][:cap]
        self.items = kept + sorted(rest, key=lambda x: -x.created)

    def bump(self, item_id):
        with self._lock:
            for i, it in enumerate(self.items):
                if it.id == item_id:
                    it.uses += 1
                    self.dirty = True
                    return

    def remove(self, item_id):
        with self._lock:
            self.items = [it for it in self.items if it.id != item_id]
            self.dirty = True

    def toggle_pin(self, item_id):
        with self._lock:
            for it in self.items:
                if it.id == item_id:
                    it.pinned = not it.pinned
                    self.dirty = True
                    return it.pinned
        return False

    def search(self, query=""):
        """Для окна истории: закреплённые сверху, далее по свежести."""
        q = (query or "").lower()
        with self._lock:
            items = list(self.items)
        if q:
            items = [it for it in items
                     if q in (it.text or "").lower()
                     or q in " ".join(it.paths or []).lower()]
        pinned = [it for it in items if it.pinned]
        rest = sorted((it for it in items if not it.pinned), key=lambda x: -x.created)
        return pinned + rest

    def newest(self):
        with self._lock:
            return self.items[0] if self.items else None

    # --- умные подсказки ------------------------------------------------------

    @staticmethod
    def _score(it, now):
        recency = max(0.0, 30.0 - (now - it.created) / 3600.0)
        return min(it.uses, 20) * 3 + (50 if it.pinned else 0) + recency

    def candidates_for(self, buffer_lower, cfg, snippets):
        """Подобрать кандидатов для буфера набора: сниппеты + спец-типы + тексты."""
        out, now, n = [], time.time(), len(buffer_lower)

        if cfg.get("suggest_snippets", True):
            for s in snippets.items:
                tr = (s.get("trigger") or "").strip()
                txt = s.get("text") or ""
                tl = tr.lower()
                if not tr or not txt or len(tl) <= n or not tl.startswith(buffer_lower):
                    continue
                out.append(Candidate(txt, f"{tr}  →  {trunc(txt, 46)}", "⚡", None, 1000 + len(tr)))

        special = ("link", "email", "color", "json") if cfg.get("suggest_special", True) else ()
        min_plain = cfg.get("suggest_plain_text", False)

        with self._lock:
            items = list(self.items)
        for it in items:
            t = it.text or ""
            if not t:
                continue
            tl = t.lower()
            if len(tl) <= n or not tl.startswith(buffer_lower):
                continue
            if it.type in special:
                out.append(Candidate(t, trunc(t, 66), it.icon, it,
                                     self._score(it, now) + 500))
            elif it.type == "text":
                if it.pinned:
                    out.append(Candidate(t, trunc(t, 66), it.icon, it,
                                         self._score(it, now) + 700))
                elif min_plain and len(t) >= 24:
                    out.append(Candidate(t, trunc(t, 66), it.icon, it,
                                         self._score(it, now)))

        # дубликаты по тексту вставки — оставляем лучший
        best = {}
        for c in out:
            if c.insert not in best or best[c.insert].score < c.score:
                best[c.insert] = c
        res = sorted(best.values(), key=lambda c: (-c.score, c.display))
        return res[: max(1, int(cfg.get("suggest_max_items", 6)))]


class Snippets:
    """Список сниппетов: триггер → текст. Файл snippets.json."""

    DEFAULTS = [
        {"trigger": ";прив", "text": "Привет! Как дела?"},
        {"trigger": ";дд", "text": "С уважением,\nUniBoard"},
    ]

    def __init__(self, path: Path = cfgmod.SNIPPETS_PATH):
        self.path = Path(path)
        self.items = []
        self.load()

    def load(self):
        try:
            if self.path.exists():
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                self.items = [d for d in data if isinstance(d, dict)
                              and d.get("trigger") and d.get("text")]
                return
        except Exception:
            pass
        self.items = [dict(d) for d in self.DEFAULTS]
        self.save()

    def save(self):
        try:
            cfgmod.Config._atomic_write(self.path,
                                        json.dumps(self.items, ensure_ascii=False, indent=2))
        except Exception:
            pass
