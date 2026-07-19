"""Generate recognizable primitive-composed demo GLBs into assets/.

These are intentionally simple (boxes/cylinders assembled into furniture) so the
placement/scale/validation pipeline has real geometry to work on without needing
external asset downloads. Swap in Tripo/Sketchfab GLBs later — the filenames
become the asset labels (underscores -> spaces).

Run:  ./venv/bin/python make_assets.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

OUT = Path(__file__).parent / "assets"
OUT.mkdir(exist_ok=True)


def box(size, center=(0, 0, 0), color=(180, 180, 190, 255)):
    b = trimesh.creation.box(extents=size)
    b.apply_translation(center)
    b.visual.face_colors = color
    return b


def cyl(radius, height, center=(0, 0, 0), color=(180, 180, 190, 255)):
    c = trimesh.creation.cylinder(radius=radius, height=height, sections=24)
    c.apply_translation(center)
    c.visual.face_colors = color
    return c


def save(name: str, meshes):
    scene = trimesh.Scene(meshes)
    path = OUT / f"{name}.glb"
    scene.export(path)
    print(f"wrote {path.name}")


# ---- Room: an open box (floor + 3 walls + back), ~4m x 3m x 4m ----
def make_room():
    W, D, H, t = 4.0, 4.0, 2.6, 0.08
    floor = box((W, t, D), (0, t / 2, 0), (120, 120, 130, 255))
    back = box((W, H, t), (0, H / 2, -D / 2), (200, 198, 205, 255))
    left = box((t, H, D), (-W / 2, H / 2, 0), (208, 206, 212, 255))
    right = box((t, H, D), (W / 2, H / 2, 0), (208, 206, 212, 255))
    save("room", [floor, back, left, right])


# ---- Coffee table: top slab + 4 legs (~0.9 x 0.45 x 0.5, 0.4 tall) ----
def make_table():
    top = box((0.9, 0.05, 0.5), (0, 0.4, 0), (120, 84, 55, 255))
    legs = []
    for sx in (-1, 1):
        for sz in (-1, 1):
            legs.append(
                box((0.06, 0.4, 0.06), (sx * 0.4, 0.2, sz * 0.2), (90, 62, 40, 255))
            )
    save("coffee_table", [top] + legs)


# ---- Lamp: base + pole + shade ----
def make_lamp():
    base = cyl(0.09, 0.03, (0, 0.015, 0), (60, 60, 70, 255))
    pole = cyl(0.015, 0.35, (0, 0.2, 0), (150, 150, 160, 255))
    shade = trimesh.creation.cone(radius=0.11, height=0.13, sections=24)
    shade.apply_translation((0, 0.44, 0))
    shade.visual.face_colors = (240, 230, 180, 255)
    save("lamp", [base, pole, shade])


# ---- Sofa: seat base + backrest + 2 arms ----
def make_sofa():
    base = box((1.6, 0.35, 0.8), (0, 0.175, 0), (70, 90, 130, 255))
    back = box((1.6, 0.45, 0.15), (0, 0.55, -0.32), (60, 80, 120, 255))
    arm_l = box((0.15, 0.4, 0.8), (-0.72, 0.35, 0), (60, 80, 120, 255))
    arm_r = box((0.15, 0.4, 0.8), (0.72, 0.35, 0), (60, 80, 120, 255))
    save("sofa", [base, back, arm_l, arm_r])


# ---- Chair: seat + back + 4 legs ----
def make_chair():
    seat = box((0.45, 0.06, 0.45), (0, 0.45, 0), (150, 120, 90, 255))
    back = box((0.45, 0.45, 0.06), (0, 0.68, -0.2), (150, 120, 90, 255))
    legs = []
    for sx in (-1, 1):
        for sz in (-1, 1):
            legs.append(
                box((0.05, 0.45, 0.05), (sx * 0.19, 0.225, sz * 0.19), (110, 88, 66, 255))
            )
    save("chair", [seat, back] + legs)


# ---- Plant: pot + foliage sphere ----
def make_plant():
    pot = cyl(0.13, 0.22, (0, 0.11, 0), (150, 90, 70, 255))
    foliage = trimesh.creation.icosphere(radius=0.22, subdivisions=2)
    foliage.apply_translation((0, 0.42, 0))
    foliage.visual.face_colors = (60, 140, 80, 255)
    save("plant", [pot, foliage])


# ---- Vase: tapered cylinder ----
def make_vase():
    body = cyl(0.09, 0.28, (0, 0.14, 0), (90, 160, 180, 255))
    neck = cyl(0.05, 0.06, (0, 0.31, 0), (90, 160, 180, 255))
    save("vase", [body, neck])


if __name__ == "__main__":
    make_room()
    make_table()
    make_lamp()
    make_sofa()
    make_chair()
    make_plant()
    make_vase()
    print("done — assets in", OUT)
