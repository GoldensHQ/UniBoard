"""UniBoard — smart customizable clipboard manager.

Orchestrator: threads (Raw Input keyboard listener, RegisterHotKey,
clipboard watcher, tray), typing-suggestion logic and pasting.
"""
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk

from . import clipboard, kbd, theme, winapi
from . import config as cfgmod
from .config import Config, load_hotkeys
from .history import Candidate, History, Snippets
from .watcher import ClipboardWatcher
from .decoder import CharDecoder
from .rawinput import RawInputListener
from .registrar import HotkeyRegistrar
from .popup import SuggestionPopup
from .history_ui import HistoryWindow
from .settings_ui import SettingsWindow

log = logging.getLogger("uniboard")

MAX_BUFFER = 64  # typing buffer length (three measurable prefixes with margin)


class Shared:
    """State for instant synchronous checks right inside the keyboard hook."""

    __slots__ = ("popup_visible", "cand_count", "popup_rect")

    def __init__(self):
        self.popup_visible = False
        self.cand_count = 0
        self.popup_rect = None


def focus_window(hwnd):
    """Move focus to a window (Alt trick to work around SetForegroundWindow limits)."""
    if not hwnd:
        return
    try:
        if winapi.fg_hwnd() == hwnd:
            return
        kbd.tap_key(kbd.VK_MENU)
        time.sleep(0.02)
        winapi.user32.SetForegroundWindow(hwnd)
        time.sleep(0.06)
    except Exception:
        pass


class App:
    def __init__(self):
        self.cfg = Config()
        self.snippets = Snippets()
        self.history = History(capacity=int(self.cfg.get("history_size", 500)))
        self.shared = Shared()
        self.ui_q = queue.Queue()      # → main thread (tk)
        self.worker_q = queue.Queue()  # → worker thread (logic and insertions)
        self.our_hwnds = set()
        self.suppress_until = 0.0
        self.hotkeys = load_hotkeys(self.cfg)

        self.buffer = ""       # what the user typed "blindly"
        self.cands = []        # current suggestion candidates
        self.sel = 0
        self.showing = False   # we consider the suggestion popup open
        self._closing = False

        self.root = None
        self.popup = None
        self.history_win = None
        self.settings_win = None
        self.rawinput = None
        self.watcher = None
        self.decoder = None
        self.registrar = None
        self.tray = None
        self.self_inject_until = 0.0  # ignore Raw Input during our own injection
        self._popup_fg = None         # window the suggestion popup is shown over

    # ================================ STARTUP =================================

    def run(self):
        log.info("Step 1/6: UI (tkinter)")
        self.root = tk.Tk()
        self.root.withdraw()  # the app itself lives in the tray
        self.popup = SuggestionPopup(self, self.root)
        self.history_win = HistoryWindow(self)
        self.settings_win = SettingsWindow(self)

        # start the keyboard layout decoder BEFORE hooks: the worker thread must know it
        log.info("Step 2/6: keyboard layout decoder")
        self.decoder = CharDecoder()
        self.decoder.start()

        log.info("Step 3/6: clipboard watcher")
        self.watcher = ClipboardWatcher(self)
        self.watcher.start()

        # Raw Input + RegisterHotKey: NO low-level hooks.
        log.info("Step 4/6: keyboard listener (Raw Input, no hooks)")
        self.rawinput = RawInputListener(
            lambda ev: self.worker_q.put(("key", ev)),
            on_error=lambda m: log.error("Raw Input: %s", m))
        self.rawinput.start()
        log.info("Step 4b: hotkeys (RegisterHotKey)")
        self.registrar = HotkeyRegistrar(self)
        self.registrar.start()

        log.info("Step 5/6: worker thread")
        threading.Thread(target=self._worker, name="UniBoard-Worker",
                         daemon=True).start()
        log.info("Step 6/6: tray icon")
        self._make_tray()
        log.info("UniBoard ready — main loop running")

        self.root.after(25, self.poll)
        try:
            self.root.mainloop()
        finally:
            self.shutdown()

    # ===================== KEYBOARD (NO HOOKS) =============================
    # Raw Input DELIVERS events asynchronously and does not wait for us — a
    # system freeze is impossible by construction. A key cannot be swallowed,
    # so all actions (suggestion insertion, history) go through RegisterHotKey.

    def _start_listeners(self):  # restart after settings change (future-proofing)
        try:
            if self.rawinput:
                self.rawinput.stop()
                self.rawinput = None
        except Exception:
            pass
        try:
            if self.registrar:
                self.registrar.stop()
                self.registrar = None
        except Exception:
            pass
        self.rawinput = RawInputListener(
            lambda ev: self.worker_q.put(("key", ev)),
            on_error=lambda m: log.error("Raw Input: %s", m))
        self.rawinput.start()
        self.registrar = HotkeyRegistrar(self)
        self.registrar.start()

    # ============================ WORKER THREAD =============================

    def _worker(self):
        while True:
            op, val = self.worker_q.get()
            try:
                if op == "key":
                    self._on_key(val)
                elif op == "popup_hidden":
                    self._forget_popup()
                elif op == "sel_moved":
                    if isinstance(val, int) and self.cands:
                        self.sel = val % len(self.cands)
                elif op == "accept_click":
                    if isinstance(val, int) and val < len(self.cands):
                        self._accept(self.cands[val])
                elif op == "paste":
                    item, target = val
                    self._do_paste(item, target)
                elif op == "clear_state":
                    self._clear()
                elif op == "hotkey":
                    self._hotkey(val)
                elif op == "exit":
                    return
            except Exception:
                log.exception("Error in worker thread")

    def _on_key(self, ev):
        # Our own injections (Backspace/text/Ctrl+V) look like regular keys to
        # Raw Input — ignore events within the window after an injection.
        if time.time() < self.self_inject_until:
            return
        if not ev.down:
            return
        fg = winapi.fg_hwnd()
        if not fg or fg in self.our_hwnds:
            self._clear()
            return
        vk = ev.vk

        # Esc cannot be swallowed (no hook), but reset the suggestion state.
        if self.showing and vk == kbd.VK_ESCAPE:
            self._clear()
            return

        if vk == kbd.VK_BACK:
            if self.buffer:
                self.buffer = self.buffer[:-1]
                self._refresh(fg)
            return
        if vk in kbd.CLEAR_VKS:
            self._clear()
            return
        if vk in kbd.MODIFIER_VKS:
            return
        if self.decoder.dead or not self.cfg.get("suggest_enabled", True):
            return
        # character decoding — only in a separate thread (see decoder.py)
        ch = self.decoder.decode(vk, ev.scan, ev.mods, ev.caps)
        if not ch:
            return
        if ch.isspace():
            self._clear()
            return
        self.buffer = (self.buffer + ch)[-MAX_BUFFER:]
        self._refresh(fg)

    # ------------------------- suggestions -----------------------------------

    def _refresh(self, fg=None):
        if fg is None:
            fg = winapi.fg_hwnd()
        buf = self.buffer.lower()
        if len(buf) < int(self.cfg.get("suggest_min_chars", 3)):
            self._hide_popup()
            return
        name = winapi.fg_process_name()
        if name and any(x in name for x in (self.cfg.get("excluded_apps") or [])):
            self._clear()
            return
        if self.cfg.get("snippet_auto", False):
            for s in self.snippets.items:
                if (s.get("trigger") or "").strip().lower() == buf:
                    self._accept(Candidate(s["text"], "", "⚡", None, 0))
                    return
        cands = self.history.candidates_for(buf, self.cfg, self.snippets)
        if not cands:
            self._hide_popup()
            return
        self.cands = cands
        self.sel = 0
        self.shared.cand_count = len(cands)
        x, y = winapi.caret_screen_pos()
        entries = [(c.icon, c.display) for c in cands]
        self.ui_q.put(("popup_show", (x, y, entries, 0)))
        self.showing = True
        self.shared.popup_visible = True

    def _hide_popup(self):
        self.shared.cand_count = 0
        self.shared.popup_visible = False
        if self.showing:
            self.showing = False
            self.ui_q.put(("popup_hide", None))

    def _clear(self):
        self.buffer = ""
        self.cands = []
        self.sel = 0
        self.shared.cand_count = 0
        self._hide_popup()

    def _forget_popup(self):
        """The window closed by itself on timeout (message from the main thread)."""
        self.showing = False
        self.buffer = ""
        self.cands = []
        self.sel = 0
        self.shared.cand_count = 0
        self.shared.popup_visible = False

    def _move_sel(self, d):
        if not self.cands:
            return
        self.sel = (self.sel + d) % len(self.cands)
        self.ui_q.put(("popup_sel", self.sel))

    def on_popup_hover(self, idx):
        """Mouse hover on a suggestion row (main thread)."""
        self.popup.update_sel(idx)
        self.worker_q.put(("sel_moved", idx))

    def _accept(self, cand):
        n = len(self.buffer)
        self._clear()
        try:
            if n:
                self.self_inject_until = time.time() + 2.0
                # Wait for Ctrl+Space to be released (otherwise Backspace may
                # get lost in some apps), then reliably "release" the
                # modifiers via injection.
                kbd.wait_modifiers_released()
                kbd.release_modifiers()
                kbd.send_backspaces(n)
                time.sleep(0.01)
            self._insert_text(cand.insert)
            kbd.restore_modifiers()
            if cand.ref is not None:
                self.history.bump(cand.ref.id)
        except Exception:
            log.exception("Failed to insert suggestion")
        finally:
            self.self_inject_until = time.time() + 0.6

    def _accept_current(self):
        """The "insert suggestion" hotkey (Ctrl+Space): the top candidate
        from the current typing buffer (or the selected one if the popup is open)."""
        if self.showing and self.cands:
            self._accept(self.cands[self.sel])

    # ------------------------- pasting ---------------------------------------

    def _insert_text(self, text):
        if self.cfg.get("insert_mode", "unicode") == "unicode":
            kbd.type_text(text)
        else:
            self._paste_via_clipboard_text(text)

    def _paste_via_clipboard_text(self, text):
        self._suppress(1.8)
        b = clipboard.backup() if self.cfg.get("restore_clipboard", True) else None
        clipboard.write_text(text)
        time.sleep(0.02)
        kbd.press_ctrl_v()
        self._suppress()
        time.sleep(0.45)
        if b is not None:
            clipboard.restore(b)

    def _suppress(self, extra=0.0):
        self.suppress_until = time.time() + extra

    def request_paste(self, item, target_hwnd):
        self.worker_q.put(("paste", (item, target_hwnd)))

    def _do_paste(self, item, target):
        self._clear()
        if target:
            focus_window(target)
        time.sleep(0.04)
        self.self_inject_until = time.time() + 3.0
        kbd.wait_modifiers_released()
        kbd.release_modifiers()  # see kbd.release_modifiers — hotkey combo
        restore = self.cfg.get("restore_clipboard", True)
        b = clipboard.backup() if restore else None
        try:
            if item.type == "image" and item.image:
                from PIL import Image
                clipboard.write_image(Image.open(item.image))
                time.sleep(0.02)
                kbd.press_ctrl_v()
            elif item.type == "files" and item.paths:
                clipboard.write_files(item.paths)
                time.sleep(0.02)
                kbd.press_ctrl_v()
            else:
                text = item.text or ""
                if not text:
                    return
                if self.cfg.get("insert_mode", "unicode") == "unicode":
                    kbd.type_text(text)
                    b = None  # clipboard was not touched
                else:
                    clipboard.write_text(text)
                    time.sleep(0.02)
                    kbd.press_ctrl_v()
            self.history.bump(item.id)
        finally:
            kbd.restore_modifiers()
            self._suppress()
            time.sleep(0.45)
            if b is not None:
                clipboard.restore(b)
            self.self_inject_until = time.time() + 0.8

    def _hotkey(self, name):
        now = time.time()
        last = getattr(self, "_last_hotkey", ("", 0))
        if last[0] == name and now - last[1] < 0.3:  # auto-repeat protection
            return
        self._last_hotkey = (name, now)
        if name == "history":
            self.ui_q.put(("open_history", winapi.fg_hwnd()))
        elif name == "paste_last":
            it = self.history.newest()
            if it:
                self._do_paste(it, None)
        elif name == "accept":
            self._accept_current()

    # ============================ MAIN THREAD ===============================

    def poll(self):
        if self._closing:
            return
        # Suggestion visible but focus moved to another window? Hide it (the
        # mouse cannot be captured without a hook — we close on active-window
        # change).
        if self.showing and self._popup_fg and winapi.fg_hwnd() != self._popup_fg:
            self._popup_fg = None
            self.worker_q.put(("clear_state", None))
        try:
            while True:
                op, val = self.ui_q.get_nowait()
                self._dispatch(op, val)
        except queue.Empty:
            pass
        self.root.after(25, self.poll)

    def _dispatch(self, op, val):
        try:
            if op == "popup_show":
                self.popup.show(val[0], val[1], val[2], val[3])
                self._popup_fg = winapi.fg_hwnd()
            elif op == "popup_sel":
                self.popup.update_sel(val)
            elif op == "popup_hide":
                self.popup.hide()
            elif op == "open_history":
                self.history_win.open(target_hwnd=val)
            elif op == "open_settings":
                self.settings_win.open()
            elif op == "history_dirty":
                if self.history_win.win and self.history_win.win.winfo_exists():
                    self.history_win.refresh()
            elif op == "shutdown":
                self.shutdown()
        except Exception:
            log.exception("UI error")

    def on_history_changed(self):
        self.history.maybe_save()
        self.ui_q.put(("history_dirty", None))

    def apply_config(self, new, autostart=None):
        self.cfg.update(new)
        self.cfg.save()
        self.history.capacity = int(self.cfg.get("history_size", 500))
        self.hotkeys = load_hotkeys(self.cfg)
        if self.registrar:
            self.registrar.reload()
        if autostart is not None and autostart != cfgmod.autostart_enabled():
            if not cfgmod.set_autostart(autostart):
                log.warning("Failed to change autostart in the registry")

    def _toggle_suggest(self):
        self.cfg.set("suggest_enabled", not self.cfg.get("suggest_enabled", True))
        self.cfg.save()
        self.worker_q.put(("clear_state", None))

    def _toggle_record(self):
        self.cfg.set("record_enabled", not self.cfg.get("record_enabled", True))
        self.cfg.save()

    # ================================= TRAY ===================================

    def _make_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw, ImageFont

            def icon_image():
                img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                d = ImageDraw.Draw(img)
                d.rounded_rectangle((2, 2, 62, 62), radius=14, fill=(47, 76, 246, 255))
                try:
                    f = ImageFont.load_default(size=40)
                except Exception:
                    f = ImageFont.load_default()
                d.text((32, 33), "U", font=f, fill="white", anchor="mm")
                return img

            menu = pystray.Menu(
                pystray.MenuItem("Clipboard history",
                                 lambda *_: self.ui_q.put(("open_history", winapi.fg_hwnd())),
                                 default=True),
                pystray.MenuItem("Settings", lambda *_: self.ui_q.put(("open_settings", None))),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Suggestions",
                                 lambda *_: self._toggle_suggest(),
                                 checked=lambda *_: bool(self.cfg.get("suggest_enabled", True))),
                pystray.MenuItem("Clipboard recording",
                                 lambda *_: self._toggle_record(),
                                 checked=lambda *_: bool(self.cfg.get("record_enabled", True))),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", lambda *_: self.ui_q.put(("shutdown", None))),
            )
            self.tray = pystray.Icon("UniBoard", icon_image(),
                                     "UniBoard — smart clipboard", menu)
            self.tray.run_detached()
            self.tray.notify("Running in the tray. Ctrl+Alt+V — history, "
                             "Ctrl+Space — insert suggestion.", "UniBoard")
            log.info("Tray active")
        except Exception:
            log.exception("Failed to start the tray icon")

    # =============================== SHUTDOWN ================================

    def shutdown(self):
        if self._closing:
            return
        self._closing = True
        try:
            self.worker_q.put_nowait(("exit", None))
        except Exception:
            pass
        try:
            if self.registrar:
                self.registrar.stop()
        except Exception:
            pass
        try:
            if self.rawinput:
                self.rawinput.stop()
        except Exception:
            pass
        try:
            if self.watcher:
                self.watcher.stop()
        except Exception:
            pass
        try:
            if self.decoder:
                self.decoder.stop()
        except Exception:
            pass
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        self.cfg.save()
        self.history.save()
        self.snippets.save()
        try:
            self.root.destroy()
        except Exception:
            pass


def main():
    cfgmod.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Hang diagnostics: UNIBOARD_FAULT=1 → dump stacks of all threads every 5 s
    if os.getenv("UNIBOARD_FAULT"):
        import faulthandler
        fh = open(cfgmod.app_dir() / "fault.log", "w", encoding="utf-8", buffering=1)
        faulthandler.enable(fh)
        faulthandler.dump_traceback_later(5, repeat=True, file=fh)
    handlers = [logging.FileHandler(cfgmod.LOG_PATH, encoding="utf-8")]
    if sys.stdout and sys.stderr:  # console run (uniboard.py)
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log.info("Starting UniBoard")
    try:
        App().run()
    except Exception:
        log.exception("Fatal error")
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, "UniBoard crashed on startup — details in the log:\n%s" % cfgmod.LOG_PATH,
                "UniBoard", 0x10)
        except Exception:
            pass


if __name__ == "__main__":
    main()
