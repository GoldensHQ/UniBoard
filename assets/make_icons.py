# -*- coding: utf-8 -*-
"""Generate UniBoard icons (PNG + ICO) from the logo design.

Reproduces assets/logo.svg with Pillow — no SVG renderer needed.
Run from the project root:  py -3 assets/make_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parent

BG_A, BG_B = (30, 36, 48), (13, 17, 23)          # dark tile gradient
ACC_A, ACC_B = (79, 140, 255), (124, 92, 255)    # blue → violet accent
WHITE = (244, 246, 250, 255)
LINE_A = (201, 210, 224, 255)
LINE_B = (213, 220, 232, 255)
BORDER = (216, 222, 233, 255)
TILE_BORDER = (42, 50, 66, 255)


def diag_gradient(size, c1, c2):
    """Smooth diagonal gradient: resize a 2x2 corner-colored image."""
    tiny = Image.new("RGB", (2, 2))
    px = tiny.load()
    px[0, 0] = c1
    px[1, 1] = c2
    px[0, 1] = tuple((a + b) // 2 for a, b in zip(c1, c2))
    px[1, 0] = px[0, 1]
    return tiny.resize(size, Image.BILINEAR)


def draw_logo(size=512):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s = size / 512.0
    d = ImageDraw.Draw(img)

    # Rounded app-tile background (gradient + border)
    bg = diag_gradient((size, size), BG_A, BG_B).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [int(16 * s)] * 2 + [int(496 * s)] * 2, radius=int(112 * s), fill=255)
    img.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([int(16 * s)] * 2 + [int(496 * s)] * 2,
                        radius=int(112 * s), outline=TILE_BORDER, width=max(1, int(4 * s)))

    # Clipboard body
    d.rounded_rectangle([int(140 * s), int(118 * s), int(372 * s), int(414 * s)],
                        radius=int(28 * s), fill=WHITE, outline=BORDER,
                        width=max(1, int(4 * s)))

    # Text lines
    d.rounded_rectangle([int(172 * s), int(196 * s), int(340 * s), int(210 * s)],
                        radius=int(7 * s), fill=LINE_A)
    d.rounded_rectangle([int(172 * s), int(228 * s), int(340 * s), int(242 * s)],
                        radius=int(7 * s), fill=LINE_B)
    d.rounded_rectangle([int(172 * s), int(260 * s), int(292 * s), int(274 * s)],
                        radius=int(7 * s), fill=LINE_B)

    # Big "U": two vertical strokes + bottom arc, accent gradient, round caps
    w = int(26 * s)
    left, right = int(204 * s), int(308 * s)
    top, mid = int(300 * s), int(346 * s)
    bbox = [left, int(294 * s), right, int(398 * s)]
    u_mask = Image.new("L", (size, size), 0)
    ud = ImageDraw.Draw(u_mask)
    ud.arc(bbox, start=0, end=180, fill=255, width=w)
    ud.line([left, top, left, mid], fill=255, width=w)
    ud.line([right, top, right, mid], fill=255, width=w)
    r = w // 2
    for cx in (left, right):
        ud.ellipse([cx - r, top - r, cx + r, top + r], fill=255)
    grad = diag_gradient((size, size), ACC_A, ACC_B).convert("RGB")
    img.paste(grad, (0, 0), u_mask)
    d = ImageDraw.Draw(img)

    # Top clip of the clipboard (accent gradient) + highlight
    clip_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(clip_mask).rounded_rectangle(
        [int(216 * s), int(96 * s), int(296 * s), int(142 * s)],
        radius=int(14 * s), fill=255)
    clip_grad = diag_gradient((size, size), ACC_A, ACC_B).convert("RGB")
    img.paste(clip_grad, (0, 0), clip_mask)
    d.rounded_rectangle([int(232 * s), int(112 * s), int(280 * s), int(126 * s)],
                        radius=int(7 * s), fill=(255, 255, 255, 140))
    return img


def draw_social():
    """GitHub social preview 1280x640: logo tile + wordmark + tagline."""
    W, H = 1280, 640
    img = diag_gradient((W, H), (24, 28, 38), (10, 13, 19)).convert("RGBA")
    d = ImageDraw.Draw(img)
    # soft accent glow behind the tile (drawn blurred, so the edge stays smooth)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([-60, 80, 420, 560], fill=(79, 140, 255, 150))
    from PIL import ImageFilter
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    img.alpha_composite(glow)
    d = ImageDraw.Draw(img)
    logo = draw_logo(512).resize((360, 360), Image.LANCZOS)
    img.alpha_composite(logo, (70, 140))

    def font(name, size):
        try:
            return ImageFont.truetype(str(Path(r"C:\Windows\Fonts") / name), size)
        except Exception:
            return ImageFont.load_default(size=size)

    f_title = font("seguisb.ttf", 104)
    f_sub = font("segoeui.ttf", 40)
    f_small = font("segoeui.ttf", 28)

    d.text((500, 205), "UniBoard", font=f_title, fill=(244, 246, 250, 255))
    d.text((504, 330), "Smart clipboard for Windows", font=f_sub,
           fill=(160, 176, 200, 255))
    d.text((504, 400), "Suggestions while typing  ·  Clipboard history  ·  Snippets",
           font=f_small, fill=(120, 132, 152, 255))
    d.text((504, 470), "No low-level hooks — your input can never freeze",
           font=f_small, fill=(110, 150, 255, 255))
    return img


def main():
    img = draw_logo(512)
    img.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon.png")
    img.save(ASSETS / "uniboard.ico",
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                    (64, 64), (128, 128), (256, 256)])
    draw_social().convert("RGB").save(ASSETS / "social-preview.png")
    print("OK:", ASSETS / "icon.png", ASSETS / "uniboard.ico",
          "and", ASSETS / "social-preview.png")


if __name__ == "__main__":
    main()
