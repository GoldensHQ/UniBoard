"""Окно настроек UniBoard и редактор сниппетов (tkinter)."""
import tkinter as tk
from tkinter import ttk

from . import config as cfgmod, winapi
from .config import Hotkey
from .theme import COLORS, FONT_MAIN, FONT_SMALL, FONT_BIG


def _dark_listbox(parent, **kw):
    base = dict(font=FONT_MAIN, bg=COLORS["panel"], fg=COLORS["fg"],
                selectbackground=COLORS["sel"], selectforeground=COLORS["fg"],
                activestyle="none", relief="flat", highlightthickness=0)
    base.update(kw)
    return tk.Listbox(parent, **base)


def _btn(parent, text, cmd, danger=False):
    b = tk.Button(parent, text=text, command=cmd, font=FONT_MAIN,
                  bg=COLORS["danger"] if danger else COLORS["panel2"],
                  fg=COLORS["fg"], activebackground=COLORS["sel"],
                  activeforeground=COLORS["fg"], relief="flat", padx=12, pady=3,
                  cursor="hand2")
    return b


class SettingsWindow:
    def __init__(self, app):
        self.app = app
        self.win = None

    def open(self):
        if self.win and self.win.winfo_exists():
            self.win.deiconify()
            self.win.lift()
            return
        w = tk.Toplevel(self.app.root)
        self.win = w
        w.title("UniBoard — Настройки")
        w.configure(bg=COLORS["bg"], padx=14, pady=12)
        w.geometry("560x640")
        w.transient(self.app.root)
        hwnd = winapi.tk_root_hwnd(w)
        if hwnd:
            self.app.our_hwnds.add(hwnd)
        w.protocol("WM_DELETE_WINDOW", self.close)

        canvas = tk.Canvas(w, bg=COLORS["bg"], highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(w, command=canvas.yview, width=12,
                          troughcolor=COLORS["bg"], bg=COLORS["border"])
        sb.pack(side="right", fill="y")
        body = tk.Frame(canvas, bg=COLORS["bg"])
        canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        canvas.configure(yscrollcommand=sb.set)

        c = dict(self.app.cfg.data)  # черновик значений

        def header(text):
            tk.Label(body, text=text, bg=COLORS["bg"], fg=COLORS["accent"],
                     font=FONT_BIG, anchor="w").pack(fill="x", pady=(14, 2))

        def check(key, label):
            v = tk.BooleanVar(value=bool(c.get(key)))
            tk.Checkbutton(body, text=label, variable=v, bg=COLORS["bg"],
                           fg=COLORS["fg"], activebackground=COLORS["bg"],
                           activeforeground=COLORS["fg"], selectcolor=COLORS["panel"],
                           font=FONT_MAIN, anchor="w").pack(fill="x")
            return v

        def entry_row(label, key, width=24):
            row = tk.Frame(body, bg=COLORS["bg"])
            row.pack(fill="x", pady=1)
            tk.Label(row, text=label, bg=COLORS["bg"], fg=COLORS["muted"],
                     font=FONT_MAIN, width=30, anchor="w").pack(side="left")
            v = tk.StringVar(value=str(c.get(key)))
            e = tk.Entry(row, textvariable=v, font=FONT_MAIN, bg=COLORS["panel"],
                         fg=COLORS["fg"], insertbackground=COLORS["fg"],
                         relief="flat", width=width)
            e.pack(side="left", ipady=3)
            return v

        def spin_row(label, key, lo, hi, width=6):
            row = tk.Frame(body, bg=COLORS["bg"])
            row.pack(fill="x", pady=1)
            tk.Label(row, text=label, bg=COLORS["bg"], fg=COLORS["muted"],
                     font=FONT_MAIN, width=30, anchor="w").pack(side="left")
            v = tk.IntVar(value=int(c.get(key, lo)))
            tk.Spinbox(row, from_=lo, to=hi, textvariable=v, width=width,
                       bg=COLORS["panel"], fg=COLORS["fg"], buttonbackground=COLORS["panel2"],
                       relief="flat", insertbackground=COLORS["fg"]).pack(side="left")
            return v

        # --- Подсказки ---
        header("Подсказки при печати")
        v_suggest = check("suggest_enabled", "Показывать подсказки при печати")
        v_snip = check("suggest_snippets", "Предлагать сниппеты")
        v_spec = check("suggest_special", "Предлагать ссылки, e-mail, цвета, JSON")
        v_plain = check("suggest_plain_text", "Предлагать длинные обычные тексты (от 24 символов)")
        v_auto = check("snippet_auto", "Авто-разворачивать сниппеты при точном вводе триггера")
        v_hk_acc = entry_row("Вставить подсказку (горячая клавиша)", "hotkey_accept")
        v_min = spin_row("Минимум символов для подсказки", "suggest_min_chars", 1, 12)
        v_max = spin_row("Максимум вариантов в окне", "suggest_max_items", 1, 10)
        v_to = spin_row("Автоскрытие подсказки, мс", "popup_timeout_ms", 2000, 60000, 8)

        # --- Вставка ---
        header("Вставка")
        mode = tk.StringVar(value=str(c.get("insert_mode")))
        rowm = tk.Frame(body, bg=COLORS["bg"])
        rowm.pack(fill="x")
        tk.Label(rowm, text="Способ вставки", bg=COLORS["bg"], fg=COLORS["muted"],
                 font=FONT_MAIN, width=30, anchor="w").pack(side="left")
        rb_f = tk.Frame(rowm, bg=COLORS["bg"])
        rb_f.pack(side="left")
        for val, lbl in (("unicode", "Печать посимвольно"), ("clipboard", "Через буфер")):
            tk.Radiobutton(rb_f, text=lbl, value=val, variable=mode, bg=COLORS["bg"],
                           fg=COLORS["fg"], activebackground=COLORS["bg"],
                           selectcolor=COLORS["panel"], font=FONT_MAIN).pack(side="left", padx=(0, 10))
        v_restore = check("restore_clipboard", "Возвращать прежний буфер после вставки")

        # --- Горячие клавиши ---
        header("Горячие клавиши")
        v_hk_hist = entry_row("Окно истории", "hotkey_history")
        v_hk_last = entry_row("Вставить последний элемент", "hotkey_paste_last")
        tk.Label(body, text="Формат: Ctrl+Alt+V — модификаторы Ctrl/Alt/Shift/Win + клавиша "
                 "(A–Z, 0–9, F1–F24, Space, Enter…)", bg=COLORS["bg"], fg=COLORS["muted"],
                 font=FONT_SMALL, anchor="w", justify="left").pack(fill="x")

        # --- Исключения ---
        header("Не показывать подсказки в приложениях")
        rowx = tk.Frame(body, bg=COLORS["bg"])
        rowx.pack(fill="x", pady=2)
        self.excl_list = _dark_listbox(rowx, height=4, font=FONT_SMALL)
        self.excl_list.pack(side="left", fill="both", expand=True)
        self._excl_values = list(c.get("excluded_apps") or [])
        for x in self._excl_values:
            self.excl_list.insert("end", x)
        bx = tk.Frame(rowx, bg=COLORS["bg"])
        bx.pack(side="left", padx=(8, 0))
        self._excl_entry = tk.Entry(bx, font=FONT_SMALL, bg=COLORS["panel"], fg=COLORS["fg"],
                                    relief="flat", width=16)
        self._excl_entry.pack(pady=(0, 4), ipady=2)
        _btn(bx, "+", self._excl_add).pack(fill="x", pady=1)
        _btn(bx, "−", self._excl_del).pack(fill="x", pady=1)
        tk.Label(body, text="Имя процесса (например chrome.exe). Пример по двойному клику по списку.",
                 bg=COLORS["bg"], fg=COLORS["muted"], font=FONT_SMALL, anchor="w").pack(fill="x")

        # --- История и общее ---
        header("История и общее")
        v_rec = check("record_enabled", "Записывать буфер обмена в историю")
        v_hist = spin_row("Хранить элементов", "history_size", 50, 5000, 8)
        v_watch = spin_row("Интервал опроса буфера, мс", "watch_interval_ms", 150, 2000, 8)
        v_start = tk.BooleanVar(value=cfgmod.autostart_enabled())

        self._vars = dict(suggest_enabled=v_suggest, suggest_snippets=v_snip,
                          suggest_special=v_spec, suggest_plain_text=v_plain,
                          snippet_auto=v_auto,
                          suggest_min_chars=v_min, suggest_max_items=v_max,
                          popup_timeout_ms=v_to, restore_clipboard=v_restore,
                          hotkey_accept=v_hk_acc,
                          hotkey_history=v_hk_hist, hotkey_paste_last=v_hk_last,
                          record_enabled=v_rec, history_size=v_hist,
                          watch_interval_ms=v_watch,
                          mode=mode, autostart=v_start)
        tk.Checkbutton(body, text="Запускать UniBoard вместе с Windows", variable=v_start,
                       bg=COLORS["bg"], fg=COLORS["fg"], activebackground=COLORS["bg"],
                       activeforeground=COLORS["fg"], selectcolor=COLORS["panel"],
                       font=FONT_MAIN, anchor="w").pack(fill="x")

        # --- сниппеты и кнопки ---
        header("Сниппеты")
        _btn(body, "✎  Редактор сниппетов…", lambda: SnippetEditor(self.app).open()).pack(anchor="w", pady=2)

        btns = tk.Frame(w, bg=COLORS["bg"])
        btns.pack(side="bottom", fill="x", pady=(10, 0))
        self.status = tk.Label(btns, text="", bg=COLORS["bg"], fg=COLORS["danger"], font=FONT_SMALL)
        self.status.pack(side="left")
        _btn(btns, "Сохранить", self.save).pack(side="right")
        _btn(btns, "Отмена", self.close).pack(side="right", padx=6)

    # --- исключённые приложения ---------------------------------------------------

    def _excl_add(self):
        v = self._excl_entry.get().strip().lower()
        if not v or v in self._excl_values:
            return
        self._excl_values.append(v)
        self.excl_list.insert("end", v)
        self._excl_entry.delete(0, "end")

    def _excl_del(self):
        sel = self.excl_list.curselection()
        if sel:
            i = sel[0]
            self._excl_values.pop(i)
            self.excl_list.delete(i)

    # --- сохранение -----------------------------------------------------------------

    def save(self):
        v = self._vars
        for err_key, raw in (("hotkey_accept", v["hotkey_accept"].get()),
                             ("hotkey_history", v["hotkey_history"].get()),
                             ("hotkey_paste_last", v["hotkey_paste_last"].get())):
            if raw.strip() and Hotkey.parse(raw, err_key) is None:
                self.status.configure(text=f"Не удалось разобрать горячую клавишу: {raw}")
                return
        new = {
            "suggest_enabled": bool(v["suggest_enabled"].get()),
            "suggest_snippets": bool(v["suggest_snippets"].get()),
            "suggest_special": bool(v["suggest_special"].get()),
            "suggest_plain_text": bool(v["suggest_plain_text"].get()),
            "snippet_auto": bool(v["snippet_auto"].get()),
            "suggest_min_chars": int(v["suggest_min_chars"].get()),
            "suggest_max_items": int(v["suggest_max_items"].get()),
            "popup_timeout_ms": int(v["popup_timeout_ms"].get()),
            "restore_clipboard": bool(v["restore_clipboard"].get()),
            "insert_mode": v["mode"].get(),
            "hotkey_accept": v["hotkey_accept"].get().strip(),
            "hotkey_history": v["hotkey_history"].get().strip(),
            "hotkey_paste_last": v["hotkey_paste_last"].get().strip(),
            "excluded_apps": list(self._excl_values),
            "record_enabled": bool(v["record_enabled"].get()),
            "history_size": int(v["history_size"].get()),
            "watch_interval_ms": int(v["watch_interval_ms"].get()),
        }
        self.app.apply_config(new, autostart=bool(v["autostart"].get()))
        self.close()

    def close(self):
        if self.win and self.win.winfo_exists():
            try:
                hwnd = winapi.tk_root_hwnd(self.win)
                self.app.our_hwnds.discard(hwnd)
                self.win.destroy()
            except Exception:
                pass
        self.win = None


class SnippetEditor:
    def __init__(self, app):
        self.app = app
        self.win = None

    def open(self):
        if self.win and self.win.winfo_exists():
            self.win.deiconify()
            self.win.lift()
            return
        w = tk.Toplevel(self.app.root)
        self.win = w
        w.title("UniBoard — Сниппеты")
        w.configure(bg=COLORS["bg"], padx=12, pady=10)
        w.geometry("560x420")
        w.transient(self.app.root)
        hwnd = winapi.tk_root_hwnd(w)
        if hwnd:
            self.app.our_hwnds.add(hwnd)

        top = tk.Frame(w, bg=COLORS["bg"])
        top.pack(fill="x")
        self.list = _dark_listbox(top, height=8)
        self.list.pack(side="left", fill="both", expand=True)
        side = tk.Frame(top, bg=COLORS["bg"])
        side.pack(side="left", padx=(8, 0))
        _btn(side, "+ Добавить", self.add).pack(fill="x", pady=1)
        _btn(side, "− Удалить", self.delete).pack(fill="x", pady=1)

        fields = tk.Frame(w, bg=COLORS["bg"])
        fields.pack(fill="x", pady=(8, 0))
        tk.Label(fields, text="Триггер (без пробелов, например ;прив)", bg=COLORS["bg"],
                 fg=COLORS["muted"], font=FONT_SMALL, anchor="w").pack(fill="x")
        self.trig = tk.Entry(fields, font=FONT_MAIN, bg=COLORS["panel"], fg=COLORS["fg"],
                             insertbackground=COLORS["fg"], relief="flat")
        self.trig.pack(fill="x", ipady=3)
        tk.Label(fields, text="Текст разворачивается на месте триггера", bg=COLORS["bg"],
                 fg=COLORS["muted"], font=FONT_SMALL, anchor="w").pack(fill="x", pady=(6, 0))
        self.text = tk.Text(fields, font=FONT_MAIN, bg=COLORS["panel"], fg=COLORS["fg"],
                            insertbackground=COLORS["fg"], relief="flat", height=6,
                            wrap="word")
        self.text.pack(fill="both", expand=True, pady=(2, 6))

        _btn(fields, "Сохранить выбранный", self.save_sel).pack(anchor="w")
        self.list.bind("<<ListboxSelect>>", self._load_sel)
        self.list.bind("<Double-Button-1>", self._load_sel)
        self.reload()
        self.trig.focus_set()

    def reload(self):
        self.list.delete(0, "end")
        for s in self.app.snippets.items:
            self.list.insert("end", f"  {s['trigger']}  →  {s['text'][:60]}")

    def _load_sel(self, _e=None):
        sel = self.list.curselection()
        if not sel:
            return
        s = self.app.snippets.items[sel[0]]
        self.trig.delete(0, "end")
        self.trig.insert(0, s["trigger"])
        self.text.delete("1.0", "end")
        self.text.insert("1.0", s["text"])

    def add(self):
        trig = ";новый"
        self.app.snippets.items.append({"trigger": trig, "text": ""})
        self.app.snippets.save()
        self.reload()
        self.list.selection_clear(0, "end")
        self.list.selection_set(len(self.app.snippets.items) - 1)
        self._load_sel()
        self.trig.focus_set()

    def delete(self):
        sel = self.list.curselection()
        if not sel:
            return
        self.app.snippets.items.pop(sel[0])
        self.app.snippets.save()
        self.reload()

    def save_sel(self):
        sel = self.list.curselection()
        if not sel:
            return
        trig = self.trig.get().strip()
        txt = self.text.get("1.0", "end").rstrip("\n")
        if not trig or " " in trig:
            self.trig.configure(bg=COLORS["danger"])
            self.trig.after(600, lambda: self.trig.configure(bg=COLORS["panel"]))
            return
        self.app.snippets.items[sel[0]] = {"trigger": trig, "text": txt}
        self.app.snippets.save()
        self.reload()
