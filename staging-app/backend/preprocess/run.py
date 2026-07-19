"""Reality-Reconstruction preprocessing pipeline - offline CLI.

  python -m preprocess.run --splat ../3dgs_compressed.ply --out work/room2 [--nviews 12] [--no-flux]

Emits, under <out>/:
  source_views/       RGB + depth + camera json per orbit view
  sam_detections/     SAM2 detection overlays (bounding boxes) per view
  object_crops/       per-object masked crops (SAM output = FLUX input)
  reference_images/   FLUX 3D reference images (Tripo inputs) + empty room
  montage.png         one row per object: [view | SAM detection | crop | FLUX ref]
  scene.json          portable scene graph (metric + relative positions)
"""
from __future__ import annotations

import argparse
import glob
import json
import os

import numpy as np
from PIL import Image

# Output subfolder names (one set per splat run).
DIR_VIEWS = "source_views"        # captured source images
DIR_SAM = "sam_detections"        # SAM output with bounding-box markings
DIR_CROPS = "object_crops"        # SAM per-object crops (also the FLUX input)
DIR_REFS = "reference_images"     # FLUX 3D reference outputs + empty room

from loader import load_room
from capture import capture
from segment import segment_view, overlay, crop_object
from label import label_crop
from measure import load_cam, mask_world_points, centroid_and_bbox, cluster_objects
from reference import make_reference, make_empty_room
import montage as montage_mod


def log(msg):
    print(f"[preprocess] {msg}", flush=True)


def stage_capture(cloud, out, nviews):
    vdir = os.path.join(out, DIR_VIEWS)
    if glob.glob(os.path.join(vdir, "orbit_*_cam.json")):
        log("views exist, reusing")
    else:
        log(f"capturing {nviews} views")
        capture(cloud, vdir, n=nviews)
    return vdir


def stage_detect_label(vdir, sam_dir, crop_dir):
    """Segment every view, label each crop, back-project centroids. Returns list
    of detection records."""
    os.makedirs(sam_dir, exist_ok=True)
    os.makedirs(crop_dir, exist_ok=True)
    views = sorted(glob.glob(os.path.join(vdir, "orbit_*.png")))
    records = []
    for vi, vpath in enumerate(views):
        name = os.path.splitext(os.path.basename(vpath))[0]
        dets, (W, H) = segment_view(vpath)
        depth = np.load(os.path.join(vdir, f"{name}_depth.npy"))
        cam = load_cam(vdir, name)
        labels_for_overlay = []
        for di, d in enumerate(dets):
            crop = crop_object(vpath, d)
            lbl, is_obj = label_crop(crop)
            labels_for_overlay.append(lbl if is_obj else f"~{lbl}")
            if not is_obj:
                continue
            wpts = mask_world_points(d["mask"], depth, cam)
            geo = centroid_and_bbox(wpts)
            if geo is None:
                continue
            crop_path = os.path.join(crop_dir, f"{name}_{di}_{lbl.replace(' ','_')}.png")
            crop.save(crop_path)
            records.append({"view": name, "vpath": vpath, "det_idx": di,
                            "label": lbl, "area": d["area"], "bbox": d["bbox"],
                            "crop_path": crop_path, **geo})
        overlay(vpath, dets, os.path.join(sam_dir, f"{name}.png"), labels=labels_for_overlay)
        log(f"  {name}: {len(dets)} masks, {sum(1 for l in labels_for_overlay if not l.startswith('~'))} objects")
    return records


def _aabb_iou(a, b):
    """3D IoU of two axis-aligned boxes given as (min, max) triples."""
    import numpy as np
    amn, amx = np.array(a[0], float), np.array(a[1], float)
    bmn, bmx = np.array(b[0], float), np.array(b[1], float)
    inter = np.maximum(0, np.minimum(amx, bmx) - np.maximum(amn, bmn)).prod()
    va = np.maximum(0, amx - amn).prod()
    vb = np.maximum(0, bmx - bmn).prod()
    denom = va + vb - inter
    return float(inter / denom) if denom > 1e-9 else 0.0


def _merge_same_label(objects, iou_thresh=0.35):
    """Merge two same-label detections ONLY when their 3D boxes substantially
    overlap — i.e. they're the same physical object split across views. Distinct
    duplicates (two chairs standing apart) are kept separate, so the scene graph
    preserves every instance."""
    merged = []
    for o in sorted(objects, key=lambda x: -x["best"]["area"]):
        hit = None
        for m in merged:
            if m["label"] == o["label"] and \
               _aabb_iou((m["bbox_min"], m["bbox_max"]),
                         (o["bbox_min"], o["bbox_max"])) >= iou_thresh:
                hit = m; break
        if hit is None:
            merged.append(o)
        else:
            hit["n_views"] += o["n_views"]               # keep the larger (first) as best
    return merged


def filter_records(records, min_aspect=0.16):
    """Post-hoc cleanup applicable to cached records: drop thin-sliver bboxes and
    labels outside the furniture/decor vocabulary."""
    from label import FURNITURE
    out = []
    for r in records:
        x0, y0, x1, y1 = r["bbox"]
        bw, bh = (x1 - x0 + 1), (y1 - y0 + 1)
        if min(bw, bh) / max(bw, bh) < min_aspect:
            continue
        lbl = r["label"]
        hit = next((f for f in FURNITURE if f in lbl or lbl in f), None)
        if hit is None:
            continue
        r["label"] = hit
        out.append(r)
    return out


def dedup(records, up_axis):
    from collections import Counter
    cluster_objects(records, up_axis=up_axis, eps=0.5)
    groups = {}
    for r in records:
        groups.setdefault(r["cluster"], []).append(r)
    objects = []
    for cid, recs in groups.items():
        best = max(recs, key=lambda r: r["area"])       # least-occluded view
        label = Counter(r["label"] for r in recs).most_common(1)[0][0]
        objects.append({"cluster": cid, "label": label, "best": best,
                        "n_views": len(recs), "centroid": best["centroid"],
                        "size": best["size"], "bbox_min": best["bbox_min"],
                        "bbox_max": best["bbox_max"]})
    objects = _merge_same_label(objects)
    objects.sort(key=lambda o: -o["best"]["area"])
    return objects


def build_terrain(view_path):
    """SAM-detect every object in a view and paint it out with the surrounding
    surface colour -> the bare 'terrain' (object-free room) image."""
    import numpy as np
    dets, (W, H) = segment_view(view_path)
    base = np.array(Image.open(view_path).convert("RGB"))
    if dets:
        union = np.zeros((H, W), bool)
        for d in dets:
            union |= d["mask"]
        fill = (np.median(base[~union], axis=0) if (~union).any()
                else np.array([235, 235, 235]))
        base[union] = fill.astype(np.uint8)
    return Image.fromarray(base)


def stage_empty_room(records, vdir, out, ref_dir, use_flux):
    """Pick the best-covered view, remove all objects, generate an empty room."""
    from collections import Counter
    views = sorted(os.path.basename(v)[:-4] for v in glob.glob(os.path.join(vdir, "orbit_*.png")))
    counts = Counter(r["view"] for r in records)
    best = counts.most_common(1)[0][0] if counts else (views[0] if views else None)
    if best is None:
        return None
    terrain = build_terrain(os.path.join(vdir, f"{best}.png"))
    terrain_path = os.path.join(out, DIR_CROPS, "_room_terrain.png")
    os.makedirs(os.path.dirname(terrain_path), exist_ok=True)
    terrain.save(terrain_path)
    room_path = os.path.join(ref_dir, "room_empty.png")
    log(f"generating empty room from view {best} (flux={use_flux})")
    _, method = make_empty_room(terrain, room_path, use_flux=use_flux)
    return {"view": best, "terrain_path": terrain_path, "ref_path": room_path, "method": method}


def stage_reference(objects, ref_dir, use_flux):
    """Generate all reference images concurrently — each is an independent,
    network-bound call (VLM describe + FLUX), so a thread pool collapses the
    total time from sum() to ~max()."""
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(ref_dir, exist_ok=True)

    def one(i_o):
        i, o = i_o
        crop = Image.open(o["best"]["crop_path"])
        path = os.path.join(ref_dir, f"obj_{i+1}_{o['label'].replace(' ','_')}.png")
        _, method = make_reference(crop, o["label"], path, use_flux=use_flux)
        o["ref_path"] = path
        o["ref_method"] = method
        log(f"  ref {i+1}/{len(objects)} '{o['label']}' -> {method}")
        return o

    log(f"generating {len(objects)} reference images (flux={use_flux}, parallel)")
    with ThreadPoolExecutor(max_workers=min(6, len(objects) or 1)) as ex:
        list(ex.map(one, list(enumerate(objects))))
    return objects


def make_room_glb(size_yup, path, t=0.05):
    """Measured open room shell (floor + back + left wall) sized to the room
    bounds, floor at y=0, corner at the origin — matches the scene-graph frame
    and the spec's 'measured box room, not generated'."""
    import trimesh
    sx, sy, sz = [float(v) for v in size_yup]
    parts = []
    f = trimesh.creation.box(extents=[sx, t, sz]); f.apply_translation([sx / 2, -t / 2, sz / 2]); parts.append(f)
    w1 = trimesh.creation.box(extents=[sx, sy, t]); w1.apply_translation([sx / 2, sy / 2, -t / 2]); parts.append(w1)
    w2 = trimesh.creation.box(extents=[t, sy, sz]); w2.apply_translation([-t / 2, sy / 2, sz / 2]); parts.append(w2)
    shell = trimesh.util.concatenate(parts)
    shell.visual = trimesh.visual.ColorVisuals(shell, vertex_colors=[225, 225, 228, 255])
    shell.export(path)


def write_scene(cloud, objects, out, room=None):
    """Emit a scene graph the app can load directly.

    Everything is remapped into the app's canonical frame: **Y-up, floor at
    y=0, metres**, positions are the object's bottom-centre. So { object GLBs +
    room + this json } reconstructs the layout: place each object at `position`,
    yaw by `rotationY`, and scale so its height matches `targetHeight`.
    """
    up = cloud.up_axis
    h0, h1 = [a for a in range(3) if a != up]
    floor = float(cloud.floor)
    bmin = np.percentile(cloud.pos, 1, 0)
    bmax = np.percentile(cloud.pos, 99, 0)

    def to_yup(p):
        """Leveled frame (up=cloud.up_axis) -> canonical Y-up, floor at 0."""
        p = np.asarray(p, float)
        return [float(p[h0]), float(p[up] - floor), float(p[h1])]

    def size_yup(s):
        s = np.asarray(s, float)
        return [float(s[h0]), float(s[up]), float(s[h1])]

    room_size = size_yup(bmax - bmin)
    # generate the measured room shell GLB so the app can load the room directly
    try:
        make_room_glb(room_size, os.path.join(out, "room.glb"))
        room_asset = "room.glb"
    except Exception as e:
        log(f"room glb generation failed ({e}); leaving assetUrl unset")
        room_asset = None
    scene = {
        "version": 3,
        "coordinateSystem": {"units": "meters", "upAxis": "y", "floorY": 0.0,
                             "note": "Y-up, floor at y=0; position is bottom-center; "
                                     "scale each GLB so its height == targetHeight; "
                                     "positionRelative is 0..1 within room bounds"},
        "room": {"id": "room_0",
                 "assetUrl": room_asset,                   # measured shell in this run folder
                 "kind": "glb", "floorY": 0.0,
                 "bounds": {"min": [0.0, 0.0, 0.0], "max": room_size, "size": room_size},
                 "emptyRoomImage": (os.path.relpath(room["ref_path"], out)
                                    if room and room.get("ref_path") else None)},
        "objects": [],
    }
    for i, o in enumerate(objects):
        cen = np.asarray(o["centroid"], float)
        pos = to_yup(cen); pos[1] = 0.0                    # bottom-center on floor (y=0)
        rel = [(cen[h0] - bmin[h0]) / max(bmax[h0] - bmin[h0], 1e-6),
               (cen[up] - bmin[up]) / max(bmax[up] - bmin[up], 1e-6),
               (cen[h1] - bmin[h1]) / max(bmax[h1] - bmin[h1], 1e-6)]
        sz = size_yup(o["size"])
        scene["objects"].append({
            "id": f"obj_{i+1}", "label": o["label"],
            "assetUrl": f"/assets/obj_{i+1}.glb",
            "refImage": os.path.relpath(o["ref_path"], out) if o.get("ref_path") else None,
            "transform": {"position": [round(x, 4) for x in pos],
                          "rotationY": 0.0, "scale": 1.0},
            # rawSize seeds the app's AABB so it never NaNs if loaded before the
            # GLB is measured; the importer overrides it from the real GLB.
            "rawSize": [round(x, 3) for x in sz],
            "targetHeight": round(sz[1], 3),
            "size": [round(x, 3) for x in sz],
            "footprint": [round(sz[0], 3), round(sz[2], 3)],
            "positionRelative": [round(float(r), 4) for r in rel],
            "worldBBox": {"min": to_yup(o["bbox_min"]), "max": to_yup(o["bbox_max"]),
                          "size": sz},
            "nViews": o["n_views"], "verified": "pending"})
    with open(os.path.join(out, "scene.json"), "w") as f:
        json.dump(scene, f, indent=2)
    return scene


def build_montage(objects, cloud, out, room=None):
    rows = []
    for i, o in enumerate(objects):
        b = o["best"]
        sz = o["size"]
        rows.append({
            "label": f"{i+1}. {o['label']}",
            "size_str": f"{sz[0]:.2f}x{sz[1]:.2f}x{sz[2]:.2f} m",
            "view_img": b["vpath"],
            "det_img": os.path.join(out, DIR_SAM, f"{b['view']}.png"),
            "crop_img": b["crop_path"],
            "ref_img": o.get("ref_path"),
        })
    if room:
        rows.append({
            "label": "empty room",
            "size_str": "objects removed",
            "view_img": os.path.join(out, DIR_VIEWS, f"{room['view']}.png"),
            "det_img": os.path.join(out, DIR_SAM, f"{room['view']}.png"),
            "crop_img": room.get("terrain_path"),
            "ref_img": room.get("ref_path"),
        })
    montage_mod.build(rows, os.path.join(out, "montage.png"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--splat", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--nviews", type=int, default=12)
    ap.add_argument("--half", type=float, default=3.0, help="room half-extent (m)")
    ap.add_argument("--no-flux", action="store_true")
    ap.add_argument("--reuse-records", action="store_true",
                    help="skip SAM+VLM, reuse cached records.pkl (fast dedup/ref iteration)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    log(f"loading {args.splat}")
    cloud = load_room(args.splat, half=args.half)
    log(f"up={'XYZ'[cloud.up_axis]} floor={cloud.floor:.2f} size={np.round(cloud.size,2)}")

    vdir = stage_capture(cloud, args.out, args.nviews)
    import pickle
    rec_path = os.path.join(args.out, "records.pkl")
    if args.reuse_records and os.path.exists(rec_path):
        log("reusing cached detection records")
        records = pickle.load(open(rec_path, "rb"))
    else:
        log("segmenting + labeling")
        records = stage_detect_label(vdir, os.path.join(args.out, DIR_SAM),
                                     os.path.join(args.out, DIR_CROPS))
        for r in records:
            r.pop("mask", None)                          # drop heavy arrays before caching
        pickle.dump(records, open(rec_path, "wb"))
    log(f"{len(records)} object detections across views")
    records = filter_records(records)
    log(f"{len(records)} after sliver/vocabulary filtering")
    objects = dedup(records, cloud.up_axis)
    log(f"{len(objects)} unique objects after 3D dedup: "
        + ", ".join(o["label"] for o in objects))
    ref_dir = os.path.join(args.out, DIR_REFS)
    objects = stage_reference(objects, ref_dir, use_flux=not args.no_flux)
    room = stage_empty_room(records, vdir, args.out, ref_dir, use_flux=not args.no_flux)
    scene = write_scene(cloud, objects, args.out, room)
    build_montage(objects, cloud, args.out, room)
    log(f"DONE -> {args.out}/montage.png  scene.json  "
        f"({len(scene['objects'])} objects + 1 empty room)")


if __name__ == "__main__":
    main()
