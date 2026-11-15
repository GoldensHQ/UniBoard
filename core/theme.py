"""UniBoard dark theme for tkinter windows."""

COLORS = {
    "bg": "#1e1f24",        # window background
    "panel": "#26282e",     # panels / lists
    "panel2": "#2c2f36",    # selected item
    "fg": "#e8eaed",        # main text
    "muted": "#9aa0a6",     # muted text
    "accent": "#4f8cff",    # accent (blue)
    "sel": "#2f3b52",       # row selection
    "border": "#3a3d45",    # borders
    "danger": "#e5717a",    # delete / error
    "ok": "#7bd88f",        # success
}

FONT_MAIN = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 8)
FONT_BIG = ("Segoe UI", 11)
FONT_MONO = ("Consolas", 9)


def apply_dark(root):
    """Paint the window with the dark theme."""
    root.configure(bg=COLORS["bg"])


def trunc(s, n):
    """Truncate a string to n characters, adding an ellipsis."""
    s = (s or "").replace("\r", "").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"
