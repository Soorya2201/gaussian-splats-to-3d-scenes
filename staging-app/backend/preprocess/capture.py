"""Stage 1 - capture pose-logged views of the focused room.

Up-axis-aware oblique 'dollhouse' orbit. Writes per-view RGB + depth + camera
json. Because we own the camera, every pixel back-projects exactly (Option B).
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

from loader import Cloud, load_room
from renderer import look_at, intrinsics, render


def _basis(up_axis):
    """Return (up_vec, horiz0_idx, horiz1_idx)."""
    up = np.zeros(3); up[up_axis] = 1.0
    horiz = [a for a in range(3) if a != up_axis]
    return up, horiz[0], horiz[1]


def orbit_cameras(cloud: Cloud, radius, n=12, elev=0.55, look_h=0.9):
    up, h0, h1 = _basis(cloud.up_axis)
    c = cloud.center
    tgt = c.copy(); tgt[cloud.up_axis] = cloud.floor + look_h
    eye_up = cloud.floor + elev * radius
    cams = []
    for i in range(n):
        a = 2 * np.pi * i / n
        eye = c.copy().astype(float)
        eye[h0] = c[h0] + radius * np.cos(a)
        eye[h1] = c[h1] + radius * np.sin(a)
        eye[cloud.up_axis] = eye_up
        cams.append((f"orbit_{i:02d}", eye, tgt.copy(), up))
    return cams


def capture(cloud: Cloud, out_dir, n=12, W=1280, H=960, fov=62, point_px=2):
    os.makedirs(out_dir, exist_ok=True)
    _, h0, h1 = _basis(cloud.up_axis)
    radius = 0.72 * max(cloud.size[h0], cloud.size[h1]) + 0.6
    cams = orbit_cameras(cloud, radius, n=n)
    fx, fy, cx, cy = intrinsics(W, H, fov)
    manifest = []
    for name, eye, tgt, up in cams:
        c2w = look_at(eye, tgt, up)
        rgb, depth = render(cloud.pos, cloud.rgb, c2w, W, H, fov, point_px=point_px,
                            scale=cloud.scale, opacity=cloud.opacity)
        Image.fromarray(rgb).save(os.path.join(out_dir, f"{name}.png"))
        np.save(os.path.join(out_dir, f"{name}_depth.npy"), depth)
        cam = {"name": name, "width": W, "height": H, "fov_deg": fov,
               "fx": fx, "fy": fy, "cx": cx, "cy": cy,
               "cam2world": c2w.tolist(), "eye": eye.tolist(), "target": tgt.tolist(),
               "up_axis": cloud.up_axis}
        with open(os.path.join(out_dir, f"{name}_cam.json"), "w") as f:
            json.dump(cam, f, indent=2)
        manifest.append(cam)
    meta = {"source": cloud.source, "up_axis": cloud.up_axis, "floor": cloud.floor,
            "center": cloud.center.tolist(), "size": cloud.size.tolist(),
            "views": [m["name"] for m in manifest]}
    with open(os.path.join(out_dir, "views.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return manifest


if __name__ == "__main__":
    import sys
    sp = sys.argv[1] if len(sys.argv) > 1 else "../3dgs_compressed.ply"
    out = sys.argv[2] if len(sys.argv) > 2 else "work/room2/01_views"
    cloud = load_room(sp)
    capture(cloud, out, n=int(sys.argv[3]) if len(sys.argv) > 3 else 12)
    # contact sheet
    import glob
    files = sorted(glob.glob(os.path.join(out, "orbit_*.png")))
    imgs = [Image.open(f).resize((320, 240)) for f in files]
    cols = 4; rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 320, rows * 240), (20, 20, 20))
    for i, im in enumerate(imgs):
        sheet.paste(im, ((i % cols) * 320, (i // cols) * 240))
    sheet.save(os.path.join(out, "_sheet.png"))
    print("views:", len(imgs), "->", out)
