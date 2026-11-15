# -*- coding: utf-8 -*-
"""GUI smoke-тест: окна истории, настроек и всплывающая подсказка."""
import sys
sys.path.insert(0, ".")

import tkinter as tk

from core.app import App
from core.popup import SuggestionPopup
from core.history_ui import HistoryWindow
from core.settings_ui import SettingsWindow

app = App()
app.root = tk.Tk()
app.root.withdraw()
app.popup = SuggestionPopup(app, app.root)
app.history_win = HistoryWindow(app)
app.settings_win = SettingsWindow(app)

app.history_win.open(target_hwnd=None)
app.root.update()
app.settings_win.open()
app.root.update()

app.popup.show(120, 120, [("🔗", "https://example.com/very-long-link"),
                          ("📋", "Обычный текст из истории")], 0)
app.root.update()
app.popup.update_sel(1)
app.root.update()
app.popup.hide()
app.root.update()

app.history_win.close()
app.settings_win.close()
app.root.destroy()
print("GUI OK")
