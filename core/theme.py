"""Тёмная тема UniBoard для окон tkinter."""

COLORS = {
    "bg": "#1e1f24",        # фон окна
    "panel": "#26282e",     # панели / списки
    "panel2": "#2c2f36",    # выбранный элемент
    "fg": "#e8eaed",        # основной текст
    "muted": "#9aa0a6",     # приглушённый текст
    "accent": "#4f8cff",    # акцент (синий)
    "sel": "#2f3b52",       # выделение строки
    "border": "#3a3d45",    # рамки
    "danger": "#e5717a",    # удаление / ошибка
    "ok": "#7bd88f",        # успех
}

FONT_MAIN = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 8)
FONT_BIG = ("Segoe UI", 11)
FONT_MONO = ("Consolas", 9)


def apply_dark(root):
    """Окрасить окно в тёмную тему."""
    root.configure(bg=COLORS["bg"])


def trunc(s, n):
    """Обрезать строку до n символов, добавляя многоточие."""
    s = (s or "").replace("\r", "").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"
