"""Unified splat loader: format detection, floater cleaning, up-axis detection,
and focused-room selection.

Returns a small dataclass the rest of the pipeline consumes, so nothing
downstream needs to know whether the source was .splat or compressed .ply, or
which world axis happens to be vertical.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from splat_io import load_splat
from ply_io import load_ply


@dataclass
class Cloud:
    pos: np.ndarray        # Nx3 world
    rgb: np.ndarray        # Nx3 in 0..1
    scale: np.ndarray      # Nx3 world gaussian sigma (for splat rendering)
    opacity: np.ndarray    # N in 0..1
    up_axis: int           # 0,1,2 -> which world axis is vertical
    floor: float           # world coord along up_axis of the floor
    center: np.ndarray     # room centre (world)
    size: np.ndarray       # room bbox size (world, per-axis)
    source: str


def _sanitize(pos, rgb, scale, opacity):
    """Drop gaussians with non-finite (inf/NaN) or absurdly large positions.

    Some captures contain a few degenerate splats; left in, they make numpy warn
    (and skew estimates) all through the RANSAC / rotation math."""
    finite = np.isfinite(pos).all(axis=1)
    # also reject blown-up coordinates (float32 overflow risk downstream)
    finite &= (np.abs(pos) < 1e6).all(axis=1)
    if finite.all():
        return pos, rgb, scale, opacity
    return pos[finite], rgb[finite], scale[finite], opacity[finite]


def _load_any(path):
    """Return (pos, rgb, scale, opacity), sanitized of non-finite points."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".ply":
        pos, rgb, scale, opacity = load_ply(path, want_opacity_min=0.5)
    else:
        pos, rgb, scale = load_splat(path)
        opacity = np.ones(len(pos), np.float32)
    return _sanitize(pos, rgb, scale, opacity)


def clean_floaters(pos, rgb, scale=None, opacity=None, cell=0.12, min_count=12):
    """Drop points sitting in sparse voxels (isolated capture floaters/streaks)."""
    keys = np.floor(pos / cell).astype(np.int64)
    keys -= keys.min(0)
    dims = keys.max(0) + 1
    flat = keys[:, 0] * (dims[1] * dims[2]) + keys[:, 1] * dims[2] + keys[:, 2]
    _, inv, counts = np.unique(flat, return_inverse=True, return_counts=True)
    keep = counts[inv] >= min_count
    if scale is None:
        return pos[keep], rgb[keep]
    return pos[keep], rgb[keep], scale[keep], opacity[keep]


def detect_up_axis(pos):
    """Fallback vertical estimate: axis with the smallest robust extent (rooms
    are wider than tall). Only used when floor-plane RANSAC fails."""
    ext = np.percentile(pos, 98, 0) - np.percentile(pos, 2, 0)
    return int(np.argmin(ext))


def _ransac_plane(P, iters=250, thresh=0.03, rng=None):
    """Return (normal, offset, inlier_mask) of the largest planar region."""
    rng = rng or np.random.default_rng(0)
    best_cnt, best = 0, None
    n = len(P)
    # numpy 2.0 emits spurious divide/overflow warnings from its matmul BLAS path
    # even on finite data; ignore them here (real inf/NaN is filtered on load).
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        for _ in range(iters):
            i, j, k = rng.integers(0, n, 3)
            v1, v2 = P[j] - P[i], P[k] - P[i]
            nrm = np.cross(v1, v2)
            ln = np.linalg.norm(nrm)
            if ln < 1e-8:
                continue
            nrm = nrm / ln
            d = -nrm @ P[i]
            inl = np.abs(P @ nrm + d) < thresh
            c = int(inl.sum())
            if c > best_cnt:
                best_cnt, best = c, (nrm, d, inl)
    return best


def estimate_up(pos, n_sample=40000, thresh=0.03):
    """Estimate the world up direction as the normal of the dominant (floor)
    plane, via RANSAC + a PCA refinement, oriented so the floor sits at the
    bottom. Falls back to the extent heuristic if no strong plane is found."""
    rng = np.random.default_rng(0)
    pos = np.asarray(pos, np.float64)                       # float64: avoid overflow in matmuls
    _es = np.errstate(divide="ignore", over="ignore", invalid="ignore")
    P = pos if len(pos) <= n_sample else pos[rng.integers(0, len(pos), n_sample)]
    res = _ransac_plane(P, rng=rng, thresh=thresh)
    if res is None:
        ax = detect_up_axis(pos); v = np.zeros(3); v[ax] = 1.0
        return v
    nrm, d, inl = res
    if inl.sum() < max(200, 0.02 * len(P)):              # weak plane -> fallback
        ax = detect_up_axis(pos); v = np.zeros(3); v[ax] = 1.0
        return v
    # refine the normal with PCA on the inliers (least-variance direction)
    pts = P[inl]
    with _es:
        u, s, vt = np.linalg.svd(pts - pts.mean(0), full_matrices=False)
        nrm = vt[-1] / (np.linalg.norm(vt[-1]) + 1e-12)
        # orient so the floor plane is at the LOW end of the projection -> up = +nrm
        proj = pos @ nrm
        lo, hi = np.percentile(proj, [2, 98])
        plane_proj = float(np.median(pts @ nrm))
    if abs(plane_proj - hi) < abs(plane_proj - lo):
        nrm = -nrm
    return nrm / (np.linalg.norm(nrm) + 1e-12)


def _rot_align(a, b):
    """Rotation matrix R with R @ a = b (a, b unit vectors)."""
    a = a / (np.linalg.norm(a) + 1e-12)
    b = b / (np.linalg.norm(b) + 1e-12)
    v = np.cross(a, b)
    c = float(a @ b)
    s = float(np.linalg.norm(v))
    if s < 1e-8:                                          # already aligned or opposite
        if c > 0:
            return np.eye(3)
        # 180 deg: rotate about any axis perpendicular to a
        perp = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
        axis = np.cross(a, perp); axis /= np.linalg.norm(axis)
        K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        return np.eye(3) + 2 * K @ K
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * ((1 - c) / (s * s))


def orient_cloud(pos, snap_deg=8.0, canonical=1):
    """Return (pos_oriented, up_axis_index).

    Detect the up direction; if it's already near a world axis (clean
    axis-aligned capture) keep the cloud as-is and just report that axis. If the
    capture is tilted (COLMAP-style), rotate the whole cloud so up lands on the
    `canonical` axis (default Y) and report that.
    """
    up = estimate_up(pos)
    if not np.all(np.isfinite(up)):                       # degenerate -> extent fallback
        return pos, detect_up_axis(pos)
    axis = int(np.argmax(np.abs(up)))
    cos_to_axis = abs(up[axis])
    if cos_to_axis >= np.cos(np.deg2rad(snap_deg)):
        return pos, axis                                  # clean -> no rotation
    target = np.zeros(3); target[canonical] = 1.0
    R = _rot_align(up, target)
    if not np.all(np.isfinite(R)):                        # bad rotation -> don't rotate
        return pos, axis
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        rotated = pos @ R.T
    return rotated.astype(pos.dtype), canonical


def focus_room(pos, rgb, scale, opacity, up, half=3.0, floor_pct=3.0):
    """Crop to the densest room-sized box on the floor plane.

    Builds a 2D density histogram on the two horizontal axes, finds the
    densest cell, and keeps a `2*half` metre box around it. Returns the crop
    plus its centre / floor / size.
    """
    horiz = [a for a in range(3) if a != up]
    h0, h1 = horiz
    x, y = pos[:, h0], pos[:, h1]
    bins = 60
    H, xe, ye = np.histogram2d(x, y, bins=bins)
    # smooth a little so we pick a dense *region*, not a single spike
    from scipy.ndimage import gaussian_filter
    Hs = gaussian_filter(H, 1.5)
    i, j = np.unravel_index(np.argmax(Hs), Hs.shape)
    cx = 0.5 * (xe[i] + xe[i + 1])
    cy = 0.5 * (ye[j] + ye[j + 1])
    m = (np.abs(x - cx) <= half) & (np.abs(y - cy) <= half)
    pos, rgb, scale, opacity = pos[m], rgb[m], scale[m], opacity[m]
    floor = np.percentile(pos[:, up], floor_pct)
    center = pos.mean(0)
    size = np.percentile(pos, 98, 0) - np.percentile(pos, 2, 0)
    return pos, rgb, scale, opacity, center, floor, size


def load_room(path, half=3.0):
    pos, rgb, scale, opacity = _load_any(path)
    pos, rgb, scale, opacity = clean_floaters(pos, rgb, scale, opacity)
    pos, up = orient_cloud(pos)                           # RANSAC floor -> level cloud
    pos, rgb, scale, opacity, center, floor, size = focus_room(pos, rgb, scale, opacity, up, half=half)
    return Cloud(pos=pos, rgb=rgb, scale=scale, opacity=opacity, up_axis=up,
                 floor=float(floor), center=center, size=size, source=os.path.abspath(path))


if __name__ == "__main__":
    import sys
    c = load_room(sys.argv[1] if len(sys.argv) > 1 else "../3dgs_compressed.ply")
    print(f"source {os.path.basename(c.source)} | pts {len(c.pos):,}")
    print(f"up_axis {'XYZ'[c.up_axis]} | floor {c.floor:.2f}")
    print(f"center {np.round(c.center,2)} | size {np.round(c.size,2)}")
