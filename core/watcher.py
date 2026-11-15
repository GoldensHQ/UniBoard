"""Clipboard watcher: notices new copies and records them into history."""
import threading
import time
import uuid

from . import clipboard, config as cfgmod
from .history import ClipboardItem, classify


class ClipboardWatcher(threading.Thread):
    def __init__(self, app, interval=None):
        super().__init__(name="UniBoard-Watcher", daemon=True)
        self.app = app
        self.interval = interval or 0.4
        self._stop = threading.Event()
        self._last_seq = 0

    def stop(self):
        self._stop.set()

    def run(self):
        self._last_seq = clipboard.seq_number()
        while not self._stop.wait(self.app.cfg.get("watch_interval_ms", 400) / 1000.0):
            try:
                self._tick()
            except Exception:
                pass

    def _tick(self):
        seq = clipboard.seq_number()
        if seq == self._last_seq:
            return
        self._last_seq = seq
        # Skip our own pastes/restores
        if time.time() < getattr(self.app, "suppress_until", 0):
            return
        if not self.app.cfg.get("record_enabled", True):
            return
        data = clipboard.read_all()
        item = None
        if data["text"]:
            text = str(data["text"])
            if len(text) > 100_000:
                return
            item = ClipboardItem(classify(text), text=text)
        elif data["files"]:
            paths = [str(p) for p in data["files"] if p]
            if paths:
                item = ClipboardItem("files", paths=paths)
        elif data["image"] is not None:
            path = self._save_image(data["image"])
            if path:
                item = ClipboardItem("image", image=str(path))
        if item is not None:
            self.app.history.add(item)
            self.app.on_history_changed()

    def _save_image(self, img):
        try:
            cfgmod.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            path = cfgmod.IMAGES_DIR / f"{uuid.uuid4().hex[:12]}.png"
            img.save(path, format="PNG")
            return path
        except Exception:
            return None
