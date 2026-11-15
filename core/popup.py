"""Suggestion popup near the caret (does not steal focus)."""
import tkinter as tk

from . import winapi
from .theme import COLORS, FONT_MAIN, FONT_SMALL


class SuggestionPopup:
    def __init__(self, app, root):
        self.app = app
        self.root = root
        self.win = None
        self.rows = []
        self.sel = 0
        self._timeout_job = None

    # --- widget creation ------------------------------------------------------

    def _ensure(self):
        if self.win and self.win.winfo_exists():
            return self.win
        w = tk.Toplevel(self.root)
        w.withdraw()
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.97)
        w.configure(bg=COLORS["border"], bd=0, highlightthickness=1,
                    highlightbackground=COLORS["border"])
        outer = tk.Frame(w, bg=COLORS["panel"], padx=3, pady=3)
        outer.pack(fill="both", expand=True)
        self.body = tk.Frame(outer, bg=COLORS["panel"])
        self.body.pack(fill="x")
        self.body.columnconfigure(0, weight=1)
        self.footer = tk.Label(outer, anchor="w",
                               text="Ctrl+Space — paste    click — pick",
                               bg=COLORS["panel"], fg=COLORS["muted"],
                               font=FONT_SMALL, padx=10, pady=3)
        self.footer.pack(fill="x")
        w.protocol("WM_DELETE_WINDOW", lambda: None)
        winapi.set_noactivate(w)  # clicking a row does not steal focus from the app
        self.win = w
        return w

    # --- show / update / hide ---------------------------------------------------

    def show(self, x, y, entries, sel):
        """entries: [(icon, display)], sel — the selected index.

        Rows are reused (grid + grid_remove), so that fast typing
        does not recreate widgets on every keypress.
        """
        w = self._ensure()
        self.sel = sel
        while len(self.rows) < len(entries):
            i = len(self.rows)
            row = tk.Label(self.body, anchor="w", font=FONT_MAIN, padx=6, pady=3,
                           fg=COLORS["fg"])
            row.bind("<Button-1>", lambda e, idx=i: self._row_click(idx))
            row.bind("<Enter>", lambda e, idx=i: self.app.on_popup_hover(idx)
                     if self.app.shared.popup_visible else None)
            row.grid(row=i, column=0, sticky="ew")
            self.rows.append(row)
        for i, (icon, text) in enumerate(entries):
            row = self.rows[i]
            row.configure(text=f" {icon}  {text} ",
                          bg=COLORS["sel"] if i == sel else COLORS["panel"])
            row.grid()
        for row in self.rows[len(entries):]:
            row.grid_remove()
        w.update_idletasks()
        pw, ph = w.winfo_reqwidth() + 10, w.winfo_reqheight()
        wl, wt, wr, wb = winapi.workarea_at(x, y)
        px = int(min(max(x, wl + 4), max(wr - pw - 4, wl + 4)))
        py = int(y) + 6
        if py + ph > wb - 6:
            py = max(wt + 4, int(y) - ph - 22)
        w.geometry(f"{pw}x{ph}+{px}+{py}")
        self.app.shared.popup_rect = (px, py, pw, ph)
        w.deiconify()
        self.app.shared.popup_visible = True
        self._reschedule_timeout()

    def update_sel(self, sel):
        self.sel = sel
        for i, row in enumerate(self.rows):
            row.configure(bg=COLORS["sel"] if i == sel else COLORS["panel"])
        self._reschedule_timeout()

    def hide(self):
        self._cancel_timeout()
        self.app.shared.popup_visible = False
        self.app.shared.popup_rect = None
        if self.win and self.win.winfo_exists():
            self.win.withdraw()

    # --- events ----------------------------------------------------------------

    def _row_click(self, idx):
        self.app.worker_q.put(("accept_click", idx))

    def _reschedule_timeout(self):
        self._cancel_timeout()
        ms = max(2000, int(self.app.cfg.get("popup_timeout_ms", 10000)))
        self._timeout_job = self.root.after(ms, self._on_timeout)

    def _cancel_timeout(self):
        if self._timeout_job:
            try:
                self.root.after_cancel(self._timeout_job)
            except Exception:
                pass
            self._timeout_job = None

    def _on_timeout(self):
        self._timeout_job = None
        if self.app.shared.popup_visible:
            self.hide()
            # tell the worker thread that the window closed itself
            self.app.worker_q.put(("popup_hidden", None))
