"""Per-object montage: one row per object, columns = the pipeline stages."""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

COLS = ["source view", "SAM detection", "SAM crop", "Tripo-ready (FLUX)"]
CW, CH = 300, 225
LABELW = 150
PAD = 8
HEADH = 28


def _fit(img, w, h, bg=(30, 30, 30)):
    im = img.convert("RGB").copy()
    im.thumbnail((w, h))
    tile = Image.new("RGB", (w, h), bg)
    tile.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return tile


def build(objects, save_path):
    """objects: list of dicts with keys label, size_str, view_img, det_img,
    crop_img, ref_img (each a PIL image or path)."""
    n = len(objects)
    W = LABELW + 4 * (CW + PAD) + PAD
    H = HEADH + n * (CH + PAD) + PAD
    sheet = Image.new("RGB", (W, H), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    # header
    draw.text((PAD, 8), "object", fill=(255, 255, 255))
    for j, name in enumerate(COLS):
        x = LABELW + j * (CW + PAD)
        draw.text((x + 6, 8), name, fill=(180, 220, 255))
    for i, obj in enumerate(objects):
        y = HEADH + i * (CH + PAD)
        draw.text((PAD, y + CH // 2 - 12), obj["label"], fill=(255, 240, 120))
        draw.text((PAD, y + CH // 2 + 4), obj.get("size_str", ""), fill=(150, 150, 150))
        for j, key in enumerate(["view_img", "det_img", "crop_img", "ref_img"]):
            src = obj.get(key)
            if src is None:
                continue
            img = Image.open(src) if isinstance(src, str) else src
            tile = _fit(img, CW, CH)
            sheet.paste(tile, (LABELW + j * (CW + PAD), y))
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    sheet.save(save_path)
    return save_path
