"""Parse the antimatter15/PlayCanvas .splat binary format.

Each splat is 32 bytes:
  - position:  3 x float32   (12 bytes)
  - scale:     3 x float32   (12 bytes)
  - color:     4 x uint8  RGBA (4 bytes)
  - rotation:  4 x uint8  quaternion, encoded (q*128)+128 (4 bytes)

We only need position + color (+ scale for point-size weighting) to render a
point-cloud proxy with a z-buffer, which is all Option B back-projection needs.
"""
from __future__ import annotations

import numpy as np

SPLAT_STRIDE = 32


def load_splat(path: str):
    """Return (positions Nx3 float32, colors Nx3 float32 in 0..1, scales Nx3 float32)."""
    raw = np.fromfile(path, dtype=np.uint8)
    n = raw.shape[0] // SPLAT_STRIDE
    raw = raw[: n * SPLAT_STRIDE].reshape(n, SPLAT_STRIDE)

    positions = raw[:, 0:12].copy().view(np.float32).reshape(n, 3)
    scales = raw[:, 12:24].copy().view(np.float32).reshape(n, 3)
    colors = raw[:, 24:28].astype(np.float32) / 255.0  # RGBA -> keep RGB
    rgb = colors[:, :3]
    return positions.astype(np.float32), rgb.astype(np.float32), scales.astype(np.float32)


def robust_bounds(positions: np.ndarray, lo=1.0, hi=99.0):
    """Percentile bounds to ignore stray floater splats."""
    mn = np.percentile(positions, lo, axis=0)
    mx = np.percentile(positions, hi, axis=0)
    return mn, mx


if __name__ == "__main__":
    import sys

    p = sys.argv[1] if len(sys.argv) > 1 else "../room.splat"
    pos, rgb, sc = load_splat(p)
    print(f"splats: {len(pos):,}")
    mn, mx = pos.min(0), pos.max(0)
    print("raw min:", np.round(mn, 3), "raw max:", np.round(mx, 3))
    rmn, rmx = robust_bounds(pos)
    print("p1  min:", np.round(rmn, 3), "p99 max:", np.round(rmx, 3))
    print("robust size (per axis):", np.round(rmx - rmn, 3))
    print("centroid:", np.round(pos.mean(0), 3))
    # crude up-axis guess: the axis with the SMALLEST robust extent is usually vertical
    ext = rmx - rmn
    print("extent order (smallest->largest axis idx):", np.argsort(ext))
    print("color sample mean:", np.round(rgb.mean(0), 3))
