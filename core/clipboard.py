"""Буфер обмена Windows: чтение/запись текста, файлов, изображений (pywin32 + Pillow)."""
import io
import struct
import time

import win32clipboard as wcb
import win32con
import pywintypes

CF_UNICODETEXT, CF_DIB, CF_HDROP = win32con.CF_UNICODETEXT, win32con.CF_DIB, win32con.CF_HDROP


def _open_retry(timeout=1.0):
    """Открыть буфер обмена, дождавшись освобождения другими приложениями."""
    deadline = time.time() + timeout
    while True:
        try:
            wcb.OpenClipboard()
            return True
        except pywintypes.error:
            if time.time() >= deadline:
                return False
            time.sleep(0.03)


def read_all():
    """Считать доступные форматы: {"text", "files", "image"(PIL Image|None)}."""
    out = {"text": None, "files": None, "image": None}
    if not _open_retry():
        return out
    try:
        if wcb.IsClipboardFormatAvailable(CF_UNICODETEXT):
            try:
                out["text"] = wcb.GetClipboardData(CF_UNICODETEXT)
            except Exception:
                pass
        if out["files"] is None and wcb.IsClipboardFormatAvailable(CF_HDROP):
            try:
                out["files"] = list(wcb.GetClipboardData(CF_HDROP))
            except Exception:
                pass
    finally:
        wcb.CloseClipboard()
    if out["text"] is None and out["files"] is None:
        try:
            from PIL import ImageGrab
            data = ImageGrab.grabclipboard()
            from PIL import Image
            if isinstance(data, Image.Image):
                out["image"] = data
        except Exception:
            pass
    return out


def _write_locked(fn):
    if not _open_retry():
        return False
    try:
        wcb.EmptyClipboard()
        fn()
        return True
    except Exception:
        return False
    finally:
        wcb.CloseClipboard()


def write_text(text):
    return _write_locked(lambda: wcb.SetClipboardData(CF_UNICODETEXT, str(text)))


def write_files(paths):
    data = _dropfiles_blob(paths)
    return _write_locked(lambda: wcb.SetClipboardData(CF_HDROP, data))


def write_image(img):
    """Записать PIL Image как CF_DIB (24-bit, без альфы)."""
    data = _image_to_dib(img)
    if data is None:
        return False
    return _write_locked(lambda: wcb.SetClipboardData(CF_DIB, data))


def _dropfiles_blob(paths):
    """CF_HDROP: структура DROPFILES + список путей (UTF-16, двойной ноль)."""
    wide = "".join(p + "\0" for p in paths)
    payload = (wide + "\0").encode("utf-16-le")
    header = struct.pack("<IiiII", 20, 0, 0, 0, 1)  # pFiles=20, pt(0,0), fNC=0, fWide=1
    return header + payload


def _image_to_dib(img):
    try:
        img = img.convert("RGB")
        w, h = img.size
        raw = img.tobytes()  # RGB, сверху вниз
        row = ((w * 3 + 3) // 4) * 4
        out = bytearray()
        for y in range(h - 1, -1, -1):  # DIB хранится снизу вверх
            r = raw[y * w * 3:(y + 1) * w * 3]
            bgr = bytearray(r)
            bgr[0::3], bgr[2::3] = r[2::3], r[0::3]
            out += bgr
            out += b"\x00" * (row - len(bgr))
        hdr = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, row * h, 2835, 2835, 0, 0)
        return bytes(hdr) + bytes(out)
    except Exception:
        return None


def _dib_to_image(dib):
    """Обернуть сырой DIB в BMP-контейнер и открыть через Pillow."""
    from PIL import Image
    bisize = struct.unpack("<I", dib[:4])[0]
    bitcount = struct.unpack("<H", dib[14:16])[0]
    clrused = struct.unpack("<I", dib[32:36])[0]
    if bitcount <= 8:
        pal = (clrused or (1 << bitcount)) * 4
    else:
        pal = clrused * 4
    offset = 14 + bisize + pal
    bmp = b"BM" + struct.pack("<IHHI", len(dib) + 14, 0, 0, offset) + dib
    return Image.open(io.BytesIO(bmp))


def backup():
    """Сохранить текущее содержимое буфера (текст, файлы, картинка)."""
    d = read_all()
    b64 = None
    if d["image"] is not None:
        try:
            buf = io.BytesIO()
            d["image"].save(buf, format="PNG")
            b64 = buf.getvalue()
        except Exception:
            b64 = None
    return {"text": d["text"], "files": d["files"], "image_png": b64}


def restore(data):
    """Восстановить содержимое буфера (наилучшим образом из известных форматов)."""
    if not data:
        return False
    if not _open_retry():
        return False
    try:
        wcb.EmptyClipboard()
        if data.get("text") is not None:
            wcb.SetClipboardData(CF_UNICODETEXT, data["text"])
        if data.get("files"):
            wcb.SetClipboardData(CF_HDROP, _dropfiles_blob(data["files"]))
        png = data.get("image_png")
        if png:
            try:
                from PIL import Image
                img = Image.open(io.BytesIO(png))
                wcb.SetClipboardData(CF_DIB, _image_to_dib(img))
            except Exception:
                pass
        return True
    except Exception:
        return False
    finally:
        wcb.CloseClipboard()


def seq_number():
    """Номер изменения буфера — быстрый способ заметить новое копирование."""
    import ctypes
    return ctypes.windll.user32.GetClipboardSequenceNumber()
