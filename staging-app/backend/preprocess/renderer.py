"""Minimal CPU point-cloud rasterizer for .splat proxies.

No GPU / no OpenGL. Projects the splat point cloud through a pinhole camera and
keeps the nearest point per pixel (z-buffer). Emits:
  - RGB   uint8   HxWx3
  - depth float32 HxW   (camera-space z in world units; 0 = no hit)
  - cam   dict    intrinsics (fx,fy,cx,cy) + extrinsics (cam->world 4x4)

Because we own the camera, back-projecting any pixel is exact (Option B).
"""
from __future__ import annotations

import numpy as np


def look_at(eye, target, up):
    """Return cam->world 4x4 (OpenCV convention: +x right, +y down, +z forward)."""
    eye = np.asarray(eye, np.float64)
    target = np.asarray(target, np.float64)
    up = np.asarray(up, np.float64)
    fwd = target - eye
    fwd = fwd / (np.linalg.norm(fwd) + 1e-9)
    right = np.cross(fwd, up)
    right = right / (np.linalg.norm(right) + 1e-9)
    down = np.cross(fwd, right)
    R = np.stack([right, down, fwd], axis=1)  # columns = cam axes in world
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = eye
    return M


def intrinsics(width, height, fov_deg):
    fov = np.deg2rad(fov_deg)
    fx = fy = (width / 2.0) / np.tan(fov / 2.0)
    cx, cy = width / 2.0, height / 2.0
    return fx, fy, cx, cy


def render(positions, colors, cam2world, width, height, fov_deg,
           point_px=2, bg=(245, 245, 245), scale=None, opacity=None, max_radius=6):
    """Rasterize to (rgb uint8 HxWx3, depth float32 HxW).

    When per-splat `scale` (world sigma, Nx3) is supplied, each Gaussian is
    drawn as a soft, screen-size-correct, opacity-weighted disc and the frame is
    composited by normalized front-biased blending -> a smooth, photographic
    splat look instead of sparse dots. Falls back to fixed-size points otherwise.
    Depth is a nearest-surface z-buffer for exact back-projection (Option B).
    """
    fx, fy, cx, cy = intrinsics(width, height, fov_deg)
    world2cam = np.linalg.inv(cam2world)

    P = np.c_[positions, np.ones(len(positions))]           # Nx4
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        cam = (world2cam @ P.T).T[:, :3]                    # Nx3 in camera space
    z = cam[:, 2]
    front = z > 1e-3
    cam, col, z = cam[front], colors[front], z[front]
    sc = scale[front] if scale is not None else None
    op = opacity[front] if opacity is not None else np.ones(len(z), np.float32)

    u = (cam[:, 0] * fx / z) + cx
    v = (cam[:, 1] * fy / z) + cy
    ui = np.round(u).astype(np.int64)
    vi = np.round(v).astype(np.int64)

    # per-splat screen radius (px): world sigma projected, ~2 sigma footprint
    if sc is not None:
        sworld = np.mean(sc, axis=1)
        radf = np.clip(sworld * fx / z * 2.0, 0.7, float(max_radius))
    else:
        radf = np.full(z.shape, float(point_px))
    RMAX = int(np.ceil(float(radf.max()))) if len(radf) else 1
    RMAX = max(1, min(RMAX, max_radius))

    inb = (ui >= -RMAX) & (ui < width + RMAX) & (vi >= -RMAX) & (vi < height + RMAX)
    ui, vi, z, col, radf, op = ui[inb], vi[inb], z[inb], col[inb], radf[inb], op[inb]

    depth = np.zeros((height, width), np.float32)
    if len(z) == 0:
        rgb = np.zeros((height, width, 3), np.uint8); rgb[:] = bg
        return rgb, depth

    # Expand each splat into its disc footprint, then paint ALL contributions in
    # one global far->near pass (nearest overwrites) -> scale-sized opaque discs
    # with correct occlusion: fills surfaces, keeps detail, no translucency fog.
    radi = np.clip(np.round(radf), 1, RMAX).astype(np.int64)
    r2 = radi * radi
    xs_l, ys_l, z_l, c_l = [], [], [], []
    for dy in range(-RMAX, RMAX + 1):
        for dx in range(-RMAX, RMAX + 1):
            d2 = dx * dx + dy * dy
            sel = r2 >= d2
            if not sel.any():
                continue
            xx, yy = ui[sel] + dx, vi[sel] + dy
            m = (xx >= 0) & (xx < width) & (yy >= 0) & (yy < height)
            if not m.any():
                continue
            xs_l.append(xx[m]); ys_l.append(yy[m])
            z_l.append(z[sel][m]); c_l.append(col[sel][m])
    xs = np.concatenate(xs_l); ys = np.concatenate(ys_l)
    zz = np.concatenate(z_l); cc = np.concatenate(c_l)

    order = np.argsort(-zz)                                 # far first -> near overwrites
    flat = ys[order] * width + xs[order]
    rgb_flat = np.zeros((height * width, 3), np.uint8)
    rgb_flat[:] = bg
    rgb_flat[flat] = np.clip(cc[order] * 255, 0, 255).astype(np.uint8)
    depth_flat = depth.reshape(-1)
    depth_flat[flat] = zz[order]
    return rgb_flat.reshape(height, width, 3), depth_flat.reshape(height, width)


def unproject(u, v, d, fx, fy, cx, cy, cam2world):
    """Pixel(s)+depth -> world point(s). u,v,d can be scalars or arrays."""
    x = (np.asarray(u) - cx) / fx * d
    y = (np.asarray(v) - cy) / fy * d
    z = np.asarray(d)
    pts = np.stack([x, y, z, np.ones_like(z)], axis=-1)
    world = pts @ cam2world.T
    return world[..., :3]
