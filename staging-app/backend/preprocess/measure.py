"""Stages 3-4 helpers: back-project masks to 3D, cluster across views, measure.

All metric recovery rides on the depth map + camera pose we saved at capture
time, so every masked pixel unprojects exactly to a world point (Option B).
"""
from __future__ import annotations

import json
import os

import numpy as np

from renderer import unproject


def load_cam(view_dir, name):
    with open(os.path.join(view_dir, f"{name}_cam.json")) as f:
        return json.load(f)


def mask_world_points(mask, depth, cam, subsample=4000):
    """Unproject the valid (hit) masked pixels to world space."""
    ys, xs = np.where(mask & (depth > 0))
    if xs.size == 0:
        return np.empty((0, 3))
    if xs.size > subsample:
        idx = np.random.default_rng(0).choice(xs.size, subsample, replace=False)
        xs, ys = xs[idx], ys[idx]
    d = depth[ys, xs]
    c2w = np.array(cam["cam2world"])
    return unproject(xs, ys, d, cam["fx"], cam["fy"], cam["cx"], cam["cy"], c2w)


def centroid_and_bbox(world_pts, lo=5, hi=95):
    """Robust centroid + axis-aligned bbox (metres), rejecting stray points."""
    if len(world_pts) < 8:
        return None
    mn = np.percentile(world_pts, lo, axis=0)
    mx = np.percentile(world_pts, hi, axis=0)
    inb = np.all((world_pts >= mn) & (world_pts <= mx), axis=1)
    pts = world_pts[inb] if inb.sum() >= 8 else world_pts
    return {
        "centroid": pts.mean(0).tolist(),
        "bbox_min": pts.min(0).tolist(),
        "bbox_max": pts.max(0).tolist(),
        "size": (pts.max(0) - pts.min(0)).tolist(),
    }


def cluster_objects(records, up_axis=None, eps=0.4):
    """Cluster detections by 3D centroid proximity (single-link, eps metres).

    Uses a KD-tree + union-find so we don't depend on scikit-learn. Each real
    object = one cluster; the same lamp seen from many views collapses to one.
    """
    from scipy.spatial import cKDTree
    if not records:
        return []
    cents = np.array([r["centroid"] for r in records])
    n = len(cents)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    tree = cKDTree(cents)
    for a, b in tree.query_pairs(eps):
        union(a, b)
    roots = {}
    labels = []
    for i in range(n):
        r = find(i)
        roots.setdefault(r, len(roots))
        labels.append(roots[r])
    for rec, l in zip(records, labels):
        rec["cluster"] = int(l)
    return labels
