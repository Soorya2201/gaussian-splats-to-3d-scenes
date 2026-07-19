"""VLM labeling via the already-wired NVIDIA NIM vision model.

The VLM is strong at naming a single cropped object and weak at whole-scene
localization, so we only ever ask it to label one crop at a time.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re

from PIL import Image
from openai import OpenAI

_ENV = "/Volumes/Soorya_1_TB/Projects/World_model_hackathon/staging-app/backend/.env"

FURNITURE = {
    "bed", "sofa", "couch", "armchair", "chair", "stool", "bench", "table",
    "coffee table", "side table", "nightstand", "desk", "dresser", "cabinet",
    "bookshelf", "shelf", "wardrobe", "lamp", "floor lamp", "chandelier",
    "pendant light", "rug", "carpet", "plant", "potted plant", "vase",
    "mirror", "picture", "picture frame", "artwork", "tv", "television",
    "ottoman", "pillow", "cushion", "curtain", "clock", "fireplace",
}
_NON = {"wall", "floor", "ceiling", "window", "door", "room", "background",
        "nothing", "unknown", "none", "frame", "corner", "baseboard", "molding"}


def _client():
    from dotenv import load_dotenv
    load_dotenv(_ENV)
    return OpenAI(base_url=os.environ["VISION_BASE_URL"],
                  api_key=os.environ["VISION_API_KEY"], timeout=90, max_retries=1)


def _to_url(img: Image.Image, max_side=512):
    im = img.convert("RGB"); im.thumbnail((max_side, max_side))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def label_crop(crop: Image.Image, model=None):
    """Return (label, is_object). Label is a short noun; is_object is False for
    walls/floor/background so the caller can drop them."""
    cli = _client()
    model = model or os.environ.get("VISION_MODEL")
    prompt = (
        "This is a single object cropped from a 3D room scan (grainy). "
        "Name the ONE main furniture or decor object shown, as a short noun phrase "
        "(1-3 words, lowercase). If it is only wall, floor, ceiling, window, door, "
        "or empty background, answer exactly 'background'. Answer with the label only.")
    try:
        r = cli.chat.completions.create(
            model=model, temperature=0, max_tokens=12,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": _to_url(crop)}}]}])
        raw = (r.choices[0].message.content or "").strip().lower()
        raw = re.sub(r"[^a-z ]", "", raw).strip()
        raw = re.sub(r"^(a|an|the)\s+", "", raw)
        if not raw:
            return "background", False
        if any(n in raw for n in _NON):
            return raw, False
        # keep only if it maps to a known furniture/decor noun (drops the VLM's
        # occasional "necklace"/"stick"/"bracelet" hallucinations on grainy crops)
        hit = next((f for f in FURNITURE if f in raw or raw in f), None)
        if hit is None:
            return raw, False
        return hit, True
    except Exception as e:
        return f"error:{e}", False
