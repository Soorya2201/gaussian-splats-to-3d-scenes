"""Stage 5 - Tripo-ready reference image, generated with an image model.

Faithful-but-reliable recipe: the VLM writes a detailed description of THIS
object's crop, then FLUX.1-dev (hosted on the user's NVIDIA NIM key) renders a
clean studio product shot from that description. Falls back to the raw masked
composite if generation fails, so the pipeline never blocks on the API.
"""
from __future__ import annotations

import base64
import io
import os

import requests
from PIL import Image
from openai import OpenAI

_ENV = "/Volumes/Soorya_1_TB/Projects/World_model_hackathon/staging-app/backend/.env"
FLUX_URL = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev"


def _env():
    from dotenv import load_dotenv
    load_dotenv(_ENV)


def _to_url(img, max_side=512):
    im = img.convert("RGB"); im.thumbnail((max_side, max_side))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def describe(crop, label):
    """VLM -> one detailed appearance sentence for the prompt."""
    _env()
    cli = OpenAI(base_url=os.environ["VISION_BASE_URL"],
                 api_key=os.environ["VISION_API_KEY"], timeout=90, max_retries=1)
    prompt = (f"Describe this {label} for a product photo in one sentence: "
              f"color, material, and style only. No background, no scene.")
    try:
        r = cli.chat.completions.create(
            model=os.environ["VISION_MODEL"], temperature=0, max_tokens=40,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": _to_url(crop)}}]}])
        return (r.choices[0].message.content or "").strip().replace("\n", " ")
    except Exception:
        return label


# ---- distinct system prompts -------------------------------------------------
# Object reference: a multi-view "reference sheet" (front + side + 3/4), the kind
# that is easy to turn into a 3D model with Tripo. Colour kept, no dimensions.
OBJECT_SYSTEM = (
    "Industrial-design product reference sheet of a single {label}. {desc} "
    "Show THREE consistent views of the same object on one plain white background: "
    "a large front orthographic view on the left, and a side view and a 3/4 "
    "perspective view on the right. Clean studio product visualization, flat even "
    "lighting, accurate colour and proportions, full object in frame, isolated, "
    "no other objects, no people, no text, no dimension lines, no measurements.")

# Empty-room reference: the bare shell only (Image #1 style) — flat walls + floor,
# a window with soft daylight, no furniture whatsoever.
ROOM_SYSTEM = (
    "An empty interior room shell, no furniture and no objects at all. {desc} "
    "Simple architectural box: two clean flat walls meeting at a corner and a "
    "flat floor, matte neutral/white surfaces, one window letting in soft daylight "
    "with gentle diffuse shadows, plain seamless background, 3/4 perspective, clean "
    "3D architectural visualization, absolutely no furniture, no decor, no people, no text.")


def flux_generate(desc, label, size=768, steps=30, seed=0, system=OBJECT_SYSTEM):
    """FLUX.1-dev -> PIL image, or None on failure."""
    _env()
    key = os.environ["VISION_API_KEY"]
    prompt = system.format(label=label, desc=desc)
    try:
        r = requests.post(FLUX_URL,
                          headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
                          json={"prompt": prompt[:900], "mode": "base", "cfg_scale": 3.5,
                                "width": size, "height": size, "steps": steps, "seed": seed},
                          timeout=120)
        if r.status_code != 200:
            return None
        b64 = r.json()["artifacts"][0]["base64"]
        img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
        # guard against degenerate (all-black / all-white / flat) generations
        import numpy as np
        arr = np.asarray(img)
        if arr.std() < 8 or arr.mean() < 12:
            return None
        return img
    except Exception:
        return None


def make_reference(crop, label, save_path, use_flux=True):
    """Return (image, method). method in {'flux','composite'}."""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    if use_flux:
        desc = describe(crop, label)
        img = flux_generate(desc, label, system=OBJECT_SYSTEM)
        if img is not None:
            img.save(save_path)
            return img, "flux"
    # fallback: padded composite on white
    comp = Image.new("RGB", (768, 768), (245, 245, 245))
    c = crop.convert("RGB"); c.thumbnail((680, 680))
    comp.paste(c, ((768 - c.width) // 2, (768 - c.height) // 2))
    comp.save(save_path)
    return comp, "composite"


def describe_room(terrain_img):
    """VLM -> a one-line description of the bare room (wall/floor colour, window),
    read from the object-free 'terrain' view SAM produced."""
    _env()
    cli = OpenAI(base_url=os.environ["VISION_BASE_URL"],
                 api_key=os.environ["VISION_API_KEY"], timeout=90, max_retries=1)
    prompt = ("This is a room with its furniture removed. In ONE sentence describe "
              "only the empty room's surfaces: wall colour, floor colour/material, "
              "and whether there is a window. Ignore any leftover artifacts.")
    try:
        r = cli.chat.completions.create(
            model=os.environ["VISION_MODEL"], temperature=0, max_tokens=50,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": _to_url(terrain_img)}}]}])
        return (r.choices[0].message.content or "").strip().replace("\n", " ")
    except Exception:
        return "plain light-coloured walls and a neutral floor with a window"


def make_empty_room(terrain_img, save_path, use_flux=True):
    """From the object-free 'terrain' view -> a clean empty-room shell image.
    Returns (image, method)."""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    if use_flux:
        desc = describe_room(terrain_img)
        img = flux_generate(desc, "room", size=1024, system=ROOM_SYSTEM)
        if img is not None:
            img.save(save_path)
            return img, "flux"
    terrain_img.convert("RGB").save(save_path)
    return terrain_img, "terrain"
