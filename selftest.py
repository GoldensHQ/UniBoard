# -*- coding: utf-8 -*-
"""Быстрая проверка логики без GUI."""
import sys
sys.path.insert(0, ".")

from core.history import History, Snippets, classify, ClipboardItem
from core.config import Hotkey, DEFAULTS, Config

assert classify("https://example.com/page") == "link"
assert classify("www.example.com") == "link"
assert classify("ivan@mail.ru") == "email"
assert classify("#AABBCC") == "color"
assert classify('{"a": 1}') == "json"
assert classify("обычный текст") == "text"
print("classify OK")

h = History()
s = Snippets()
h.add(ClipboardItem("link", text="https://example.com/very-long-link"))
h.add(ClipboardItem("text", text="Просто какой-то длинный текст про UniBoard", pinned=True))

c = h.candidates_for("htt", DEFAULTS, s)
assert any(x.insert.startswith("https://") for x in c), [x.display for x in c]
c2 = h.candidates_for("про", DEFAULTS, s)
assert any("UniBoard" in x.display for x in c2), [x.display for x in c2]
c3 = h.candidates_for("zzz", DEFAULTS, s)
assert c3 == []
print("candidates OK")

c4 = h.candidates_for(";при", DEFAULTS, s)
assert c4 and c4[0].insert == "Привет! Как дела?", [(x.icon, x.display) for x in c4]
print("snippets OK")

hk = Hotkey.parse("Ctrl+Alt+V", "history")
assert hk and hk.vk == 0x56 and hk.mods == frozenset({"ctrl", "alt"})
hk2 = Hotkey.parse("Ctrl+Shift+F2", "x")
assert hk2 and hk2.vk == 0x71 and hk2.mods == frozenset({"ctrl", "shift"})
print("hotkeys OK")

assert len(h.search("uniboard")) == 1
print("search OK")

cfg = Config()
assert cfg.get("suggest_min_chars") == 3
print("config OK")
