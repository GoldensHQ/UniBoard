"""Clipboard history window with search, pinning and pasting."""
import base64
import io
import tkinter as tk
from datetime import datetime
from pathlib import Path

from . import theme, winapi
from .theme import COLORS, FONT_MAIN, FONT_SMALL, FONT_BIG

PLACEHOLDER = "Search history…"


class HistoryWindow:
    def __init__(self, app):
        self.app = app
        self.win = None
        self.items = []
        self.sel = 0
        self.target_hwnd = None
        self._thumb = None

    # --- window -----------------------------------------------------------------

    def open(self, target_hwnd=None, bring=True):
        if self.win and self.win.winfo_exists():
            self.win.deiconify()
            self.win.lift()
            self._focus_search()
            return
        root = self.app.root
        w = tk.Toplevel(root)
        self.win = w
        w.title("UniBoard — Clipboard History")
        w.configure(bg=COLORS["bg"], padx=10, pady=10)
        w.geometry("680x480")
        self.target_hwnd = target_hwnd
        self._position(w)

        top = tk.Frame(w, bg=COLORS["bg"])
        top.pack(fill="x")
        tk.Label(top, text="🔍", bg=COLORS["bg"], fg=COLORS["muted"],
                 font=FONT_BIG).pack(side="left", padx=(0, 6))
        self.search = tk.Entry(top, font=FONT_BIG, bg=COLORS["panel"], fg=COLORS["fg"],
                               insertbackground=COLORS["fg"], relief="flat",
                               highlightthickness=1, highlightbackground=COLORS["border"])
        self.search.pack(fill="x", ipady=5)
        self._set_placeholder()
        self.search.bind("<FocusIn>", self._clear_placeholder)
        self.search.bind("<FocusOut>", self._maybe_placeholder)
        self.search.bind("<KeyRelease>", lambda e: self.refresh() if e.keysym not in
                         ("Up", "Down", "Return", "Escape", "Delete", "Control_L",
                          "Control_R", "Shift_L", "Shift_R", "p", "P") else None)
        self.search.bind("<Return>", lambda e: self.paste_selected())
        self.search.bind("<Escape>", lambda e: self.close())
        self.search.bind("<Down>", lambda e: self.move(1))
        self.search.bind("<Up>", lambda e: self.move(-1))

        mid = tk.Frame(w, bg=COLORS["bg"])
        mid.pack(fill="both", expand=True, pady=(8, 0))
        self.list = tk.Listbox(mid, font=FONT_MAIN, bg=COLORS["panel"], fg=COLORS["fg"],
                               selectbackground=COLORS["sel"], selectforeground=COLORS["fg"],
                               activestyle="none", relief="flat", highlightthickness=0)
        self.list.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(mid, command=self.list.yview, width=12,
                          troughcolor=COLORS["bg"], bg=COLORS["border"],
                          activebackground=COLORS["accent"])
        sb.pack(side="right", fill="y")
        self.list.configure(yscrollcommand=sb.set)
        self.list.bind("<<ListboxSelect>>", self._on_select)
        self.list.bind("<Double-Button-1>", lambda e: self.paste_selected())
        self.list.bind("<Return>", lambda e: self.paste_selected())
        self.list.bind("<Escape>", lambda e: self.close())
        self.list.bind("<Down>", lambda e: self.move(1))
        self.list.bind("<Up>", lambda e: self.move(-1))
        self.list.bind("<Control-p>", lambda e: self.pin_selected())
        self.list.bind("<Delete>", lambda e: self.delete_selected())

        self.preview = tk.Label(w, anchor="w", justify="left", wraplength=650,
                                bg=COLORS["bg"], fg=COLORS["muted"], font=FONT_SMALL,
                                text="", compound="left")
        self.preview.pack(fill="x", pady=(8, 2))

        foot = ("Enter / double-click — paste      Ctrl+P — pin      "
                "Delete — delete      Esc — close")
        tk.Label(w, text=foot, bg=COLORS["bg"], fg=COLORS["muted"],
                 font=FONT_SMALL, anchor="w").pack(fill="x")

        w.protocol("WM_DELETE_WINDOW", self.close)
        w.transient(root)
        hwnd = winapi.tk_root_hwnd(w)
        if hwnd:
            self.app.our_hwnds.add(hwnd)
        w.bind("<Destroy>", self._on_destroy, add="+")
        w.after(60, self._focus_search)
        self.refresh()

    def _position(self, w):
        w.update_idletasks()
        ww, wh = 680, 480
        cx = cy = None
        if self.target_hwnd:
            c = winapi.window_center(self.target_hwnd)
            if c:
                cx, cy = c
        if cx is None:
            cx, cy = winapi.cursor_pos()
        wl, wt, wr, wb = winapi.workarea_at(cx, cy)
        x = min(max(cx - ww // 2, wl), max(wr - ww, wl))
        y = min(max(cy - wh // 2, wt), max(wb - wh, wt))
        w.geometry(f"{ww}x{wh}+{x}+{y}")

    def _focus_search(self):
        if self.win and self.win.winfo_exists():
            self.search.focus_set()

    # --- search placeholder ------------------------------------------------------

    def _set_placeholder(self):
        self.search.insert(0, PLACEHOLDER)
        self.search.configure(fg=COLORS["muted"])

    def _clear_placeholder(self, _e=None):
        if self.search.get() == PLACEHOLDER:
            self.search.delete(0, "end")
            self.search.configure(fg=COLORS["fg"])

    def _maybe_placeholder(self, _e=None):
        if not self.search.get():
            self._set_placeholder()

    # --- data ------------------------------------------------------------------

    def refresh(self):
        if not (self.win and self.win.winfo_exists()):
            return
        q = "" if self.search.get() == PLACEHOLDER else self.search.get()
        self.items = self.app.history.search(q)
        self.list.delete(0, "end")
        for i, it in enumerate(self.items):
            mark = "📌 " if it.pinned else ""
            self.list.insert("end", f"  {it.icon}  {mark}{it.preview(74)}")
        self.sel = 0
        if self.items:
            self.list.selection_set(0)
            self.list.see(0)
        self._show_preview()

    def move(self, d):
        if not self.items:
            return
        self.sel = (self.sel + d) % len(self.items)
        self.list.selection_clear(0, "end")
        self.list.selection_set(self.sel)
        self.list.see(self.sel)

    def _on_select(self, _e=None):
        sel = self.list.curselection()
        if sel:
            self.sel = sel[0]
        self._show_preview()

    def _show_preview(self):
        self._thumb = None
        if not self.items:
            self.preview.configure(text="History is empty — copy something first (Ctrl+C).")
            return
        it = self.items[self.sel]
        when = datetime.fromtimestamp(it.created).strftime("%d.%m %H:%M")
        parts = [f"{when}   uses: {it.uses}"]
        if it.text:
            body = it.text if len(it.text) <= 400 else it.text[:400] + "…"
            parts.append(body.replace("\r", ""))
        elif it.paths:
            parts.append("\n".join(it.paths))
        elif it.image and Path(it.image).exists():
            try:
                from PIL import Image
                img = Image.open(it.image)
                img.thumbnail((96, 96))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                self._thumb = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
                self.preview.configure(image=self._thumb)
            except Exception:
                self.preview.configure(image="")
        self.preview.configure(text="   ".join(parts))

    # --- actions ------------------------------------------------------------------

    def paste_selected(self):
        if not self.items:
            return
        it = self.items[self.sel]
        self.close()
        self.app.request_paste(it, self.target_hwnd)

    def pin_selected(self):
        if not self.items:
            return
        self.app.history.toggle_pin(self.items[self.sel].id)
        sel_keep = self.sel
        self.refresh()
        if self.items:
            self.sel = min(sel_keep, len(self.items) - 1)
            self.list.selection_clear(0, "end")
            self.list.selection_set(self.sel)
            self._show_preview()

    def delete_selected(self):
        if not self.items:
            return
        self.app.history.remove(self.items[self.sel].id)
        self.refresh()

    # --- lifecycle ------------------------------------------------------------------

    def _on_destroy(self, _e=None):
        pass  # close() unregisters the HWND

    def close(self):
        if self.win and self.win.winfo_exists():
            try:
                hwnd = winapi.tk_root_hwnd(self.win)
                self.app.our_hwnds.discard(hwnd)
                self.win.destroy()
            except Exception:
                pass
        self.win = None
