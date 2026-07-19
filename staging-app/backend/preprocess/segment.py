"""Stage 2 - SAM2 automatic segmentation per view.

Uses SAM2's fast default auto-mask mode (dense grids are too slow on CPU/MPS).
Few masks per view is fine: we run every orbit view and dedup in 3D later, so
coverage comes from viewpoint diversity, not per-view mask count.
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image

_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        import warnings; warnings.filterwarnings("ignore")
        from ultralytics import SAM
        _MODEL = SAM("sam2.1_b.pt")
    return _MODEL


def segment_view(view_path, min_frac=0.005, max_frac=0.33, min_aspect=0.16, min_fill=0.12):
    """Return list of dicts: {mask(bool HxW), bbox(x0,y0,x1,y1), area, frac}.

    Filters out capture artifacts: whole-frame masks, thin vertical/horizontal
    slivers (chandelier chains, window mullions, floater streaks), and sparse
    masks whose pixels barely fill their bounding box.
    """
    r = _model()(view_path, verbose=False)[0]
    H, W = r.orig_shape
    out = []
    if r.masks is None:
        return out, (W, H)
    data = r.masks.data.cpu().numpy().astype(bool)
    for k in range(len(data)):
        mk = data[k]
        frac = float(mk.mean())
        if frac < min_frac or frac > max_frac:
            continue
        ys, xs = np.where(mk)
        if xs.size == 0:
            continue
        x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
        if (x0 < 3 and x1 > W - 4) and (y0 < 3 and y1 > H - 4):
            continue
        bw, bh = (x1 - x0 + 1), (y1 - y0 + 1)
        if min(bw, bh) / max(bw, bh) < min_aspect:      # thin sliver -> artifact
            continue
        if mk.sum() / (bw * bh) < min_fill:              # too sparse inside box
            continue
        out.append({"mask": mk, "bbox": (x0, y0, x1, y1), "area": int(mk.sum()), "frac": frac})
    out.sort(key=lambda d: -d["area"])
    return out, (W, H)


def overlay(view_path, dets, save_path, labels=None):
    """Save a detection overlay: translucent masks + boxes (+ labels)."""
    from PIL import ImageDraw, ImageFont
    base = np.array(Image.open(view_path).convert("RGB"))
    rng = np.random.default_rng(7)
    for d in dets:
        c = rng.integers(60, 255, 3)
        base[d["mask"]] = (0.5 * base[d["mask"]] + 0.5 * c).astype(np.uint8)
    img = Image.fromarray(base)
    draw = ImageDraw.Draw(img)
    for i, d in enumerate(dets):
        x0, y0, x1, y1 = d["bbox"]
        draw.rectangle([x0, y0, x1, y1], outline=(255, 60, 60), width=3)
        tag = labels[i] if labels else f"#{i}"
        draw.text((x0 + 3, max(0, y0 - 12)), tag, fill=(255, 255, 0))
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    img.save(save_path)


def crop_object(view_path, det, pad=0.08, bg=(245, 245, 245)):
    """Masked object on a clean background, tight-cropped with padding."""
    base = np.array(Image.open(view_path).convert("RGB"))
    H, W = base.shape[:2]
    comp = np.full_like(base, bg, dtype=np.uint8)
    comp[det["mask"]] = base[det["mask"]]
    x0, y0, x1, y1 = det["bbox"]
    pw, ph = int((x1 - x0) * pad) + 6, int((y1 - y0) * pad) + 6
    x0, y0 = max(0, x0 - pw), max(0, y0 - ph)
    x1, y1 = min(W, x1 + pw), min(H, y1 + ph)
    return Image.fromarray(comp[y0:y1, x0:x1])
