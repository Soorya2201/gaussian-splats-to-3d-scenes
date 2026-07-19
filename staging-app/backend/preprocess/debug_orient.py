"""Render the splat from several candidate up-axes / angles into one contact
sheet so we can eyeball orientation and framing before committing to an orbit.
"""
from __future__ import annotations

import os
import numpy as np
from PIL import Image

from splat_io import load_splat, robust_bounds
from renderer import look_at, render

OUT = "preprocess/_debug"
W, H, FOV = 480, 360, 60


def downsample(pos, col, k=600_000):
    if len(pos) <= k:
        return pos, col
    idx = np.random.default_rng(0).choice(len(pos), k, replace=False)
    return pos[idx], col[idx]


def main():
    os.makedirs(OUT, exist_ok=True)
    pos, col, _ = load_splat("../room.splat")
    pos, col = downsample(pos, col)
    mn, mx = robust_bounds(pos)
    center = (mn + mx) / 2.0
    diag = np.linalg.norm(mx - mn)
    r = diag * 0.6

    # candidate up axes
    ups = {"Yup": [0, 1, 0], "Zup": [0, 0, 1], "Ynegup": [0, -1, 0]}
    tiles = []
    for name, up in ups.items():
        up = np.array(up, float)
        # pick two horizontal axes orthogonal-ish to up for orbit
        for ang in (0, 90, 180, 270):
            a = np.deg2rad(ang)
            if abs(up[1]) > 0.5:  # Y up -> orbit in XZ
                eye = center + np.array([np.cos(a), 0.15, np.sin(a)]) * r
            else:                  # Z up -> orbit in XY
                eye = center + np.array([np.cos(a), np.sin(a), 0.15]) * r
            rgb, _ = render(pos, col, look_at(eye, center, up), W, H, FOV, point_px=1)
            img = Image.fromarray(rgb)
            tiles.append((f"{name}_{ang}", img))

    # also a top-down for each up
    cols = 4
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * W, rows * H), (30, 30, 30))
    for i, (label, img) in enumerate(tiles):
        sheet.paste(img, ((i % cols) * W, (i // cols) * H))
    sheet.save(os.path.join(OUT, "orientation_sheet.png"))
    print("wrote", os.path.join(OUT, "orientation_sheet.png"), "center=", np.round(center, 2), "r=", round(r, 2))


if __name__ == "__main__":
    main()
