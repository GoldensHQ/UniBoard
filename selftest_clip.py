# -*- coding: utf-8 -*-
"""Clipboard test: text, files, image, backup."""
import sys
sys.path.insert(0, ".")

from core import clipboard
from PIL import Image

# preserve the user's current clipboard contents
saved = clipboard.backup()

try:
    clipboard.write_text("UniBoard test ✓ 語")
    d = clipboard.read_all()
    assert d["text"] == "UniBoard test ✓ 語", repr(d["text"])
    print("text OK")

    clipboard.write_files(["C:\\Windows", "C:\\Program Files"])
    d2 = clipboard.read_all()
    assert d2["files"] is not None and "C:\\Windows" in d2["files"], d2["files"]
    print("files OK")

    img = Image.new("RGB", (50, 30), (200, 30, 90))
    dib = clipboard._image_to_dib(img)
    back = clipboard._dib_to_image(dib)
    assert back.size == (50, 30)
    assert back.getpixel((10, 10)) == (200, 30, 90), back.getpixel((10, 10))
    print("dib roundtrip OK")

    clipboard.write_image(img)
    d3 = clipboard.read_all()
    assert d3["image"] is not None and d3["image"].size == (50, 30), d3
    print("write_image OK")

    b = clipboard.backup()
    clipboard.write_text("second")
    clipboard.restore(b)
    d4 = clipboard.read_all()
    assert d4["image"] is not None and d4["text"] is None, (d4["text"], d4["image"])
    print("backup/restore OK")
finally:
    clipboard.restore(saved)
    print("clipboard restored")
