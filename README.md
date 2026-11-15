# UniBoard — smart clipboard for Windows

UniBoard is a customizable clipboard manager that lives in the tray and helps
you paste what you copied faster: while you type, it shows a suggestion, and
`Ctrl+Space` inserts it for you.

## Features

- **Smart suggestions while typing.** Copy a link → start typing it (`htt…`)
  → a suggestion pops up → `Ctrl+Space` — the full link is inserted.
- **Clipboard history** (`Ctrl+Alt+V`): a window with search, preview,
  pinning (`Ctrl+P`), deletion (`Delete`) and pasting (`Enter`).
- **Snippets**: a short trigger expands into long text
  (e.g. `;addr` → your full address). Editor lives in Settings.
- **Smart content detection**: links, e-mails, HEX colors, JSON, images and
  copied files — each gets its own icon and priority in suggestions.
- **Paste the newest item** (`Ctrl+Alt+X`) without opening any window.
- **Settings**: hotkeys, insertion mode, per-app exclusions, autostart with
  Windows, history limits — all in the tray menu → Settings.

## Install & run

Requires Python 3.10+.

```bat
cd UniBoard
run_uniboard.bat
```

The script installs the dependencies (`pillow`, `pystray`, `pywin32`) on the
first run and starts the app without a console window. A "U" tray icon appears
after launch.

**Packaged exe (recommended).** Build it once with PyInstaller — the exe carries
the UniBoard logo (taskbar, tray) and needs no Python on the machine:

```bat
py -3 -m pip install pyinstaller
py -3 -m PyInstaller --noconfirm --onefile --windowed --name UniBoard ^
    --icon assets\uniboard.ico --add-data "assets;assets" uniboard.pyw
```

The result is `dist\UniBoard.exe` (the committed `UniBoard.spec` has the same
settings: `py -3 -m PyInstaller UniBoard.spec`). For debugging, run with a
console: `py -3 uniboard.py` (the log is also printed to the screen; the full
log is always in `%APPDATA%\UniBoard\uniboard.log`).

## How to use

| Action | How |
|---|---|
| Insert a suggestion | type the beginning of something you copied → `Ctrl+Space` |
| Pick another candidate | click the row with the mouse |
| Dismiss the suggestion | Space, clicking elsewhere, auto-timeout |
| Open history | `Ctrl+Alt+V` (or double-click the tray icon) |
| Paste the newest item | `Ctrl+Alt+X` |
| Pin in history | `Ctrl+P` |
| Pause suggestions / recording | the tray icon menu |

Suggestions trigger on the **beginning** of copied text (case-insensitive).
Space resets the typing buffer so suggestions stay out of the way of normal
typing. By default, plain long texts are offered only when pinned; links,
e-mails, colors, JSON and snippets are always offered (all of this is
configurable in Settings).

## Settings (what can be changed)

- Minimum typed characters before a suggestion appears, and the number of rows.
- The "insert suggestion" hotkey (`Ctrl+Space` by default).
- Insertion mode: typing character by character (reliable for text) or via the
  clipboard (fast for large payloads; the previous clipboard is restored).
- Auto-expanding snippets on an exact trigger (espanso/AHK style).
- Excluded apps — by process name (password managers are excluded by default).
- Autostart with Windows, history size, clipboard polling interval.

## How it works (internals)

- **No low-level hooks at all.** Early versions used `WH_KEYBOARD_LL` and
  caused system-wide input freezes on some machines (the system synchronously
  waits for the hook callback on every keystroke). Instead, UniBoard now uses:
  - **Raw Input** (`WM_INPUT`, `RIDEV_INPUTSINK`): the OS *delivers* keyboard
    events to our hidden window asynchronously and waits for nothing — an
    input freeze is impossible by construction; if our thread slows down,
    only we suffer.
  - **RegisterHotKey** — the official API for hotkeys
    (`Ctrl+Space`, `Ctrl+Alt+V`, `Ctrl+Alt+X`).
- Since a keystroke cannot be swallowed without a hook, Tab/↑/↓/Esc pass
  through to applications as usual; the suggestion is inserted with the
  `Ctrl+Space` hotkey.
- Keyboard-layout decoding (including Cyrillic layouts) happens in a separate
  thread with a timeout (`ToUnicodeEx` never runs on the main thread).
- Our own injected keys (Backspace/text/Ctrl+V) are also visible to Raw Input —
  they are filtered out by a short time window after each insertion, so the
  app never loops on its own input.
- The typing buffer (recent characters without a space) is matched against
  history and snippets; the suggestion popup is drawn next to the caret
  (`GetGUIThreadInfo`) and **never steals focus** from the target app.
- Inserting a suggestion: the exact number of `Backspace` events followed by
  the text as `KEYEVENTF_UNICODE` events — works with any layout.
- Before injecting, UniBoard waits for the physical release of the hotkey keys
  and re-releases any modifiers (otherwise a held `Ctrl` turns the typed text
  into `Ctrl+char` shortcuts) — the same trick espanso and AutoHotkey use.
- The clipboard watcher tracks `GetClipboardSequenceNumber` and stores text,
  files (CF_HDROP) and images (CF_DIB → PNG) under `%APPDATA%\UniBoard`.

## If something goes wrong

Kill the process via Task Manager: `pythonw.exe` from the UniBoard folder or
the `pyw.exe` task. Log: `%APPDATA%\UniBoard\uniboard.log`. Your keyboard and
mouse keep working no matter what: there are no hooks left that could freeze
system input.

## Limitations

- Windows running **as administrator** don't see suggestions (UIPI) — run
  UniBoard as administrator too if you need them there.
- Suggestions cannot be programmatically disabled in password fields: keep
  password managers in the exclusion list and pause suggestions from the tray
  when it matters.
- Apps that edit text on the fly (Word autocorrect) may slightly confuse the
  Backspace count.
- Images/files are pasted via the clipboard (Ctrl+V).

## Project layout

```
UniBoard/
├── uniboard.py / uniboard.pyw   — entry points (with / without console)
├── run_uniboard.bat             — installs dependencies + launches
├── requirements.txt
├── assets/logo.svg              — logo
├── selftest.py                  — quick non-GUI logic checks
└── core/
    ├── app.py          — orchestrator: threads, suggestion logic, tray
    ├── config.py       — settings, hotkeys, autostart
    ├── history.py      — history, snippets, classification, candidate ranking
    ├── rawinput.py     — keyboard listener via Raw Input (no hooks)
    ├── registrar.py    — hotkeys via RegisterHotKey
    ├── kbd.py          — input synthesis (SendInput)
    ├── decoder.py      — layout decoding in a dedicated thread (safe)
    ├── winapi.py       — caret, windows, monitors, processes
    ├── clipboard.py    — clipboard read/write (text, files, images)
    ├── watcher.py      — clipboard watcher
    ├── popup.py        — suggestion popup
    ├── history_ui.py   — history window with search
    ├── settings_ui.py  — settings window and snippet editor
    └── theme.py        — dark theme
```

## Ideas for future versions

- HTML clipboard preview and pasting as rich text (CF_HTML).
- Dynamic snippets (date/time, input prompts on expansion).
- Cloud sync of history across PCs.
- Usage statistics: what and how often you paste.

## License

MIT — see [LICENSE](LICENSE).
