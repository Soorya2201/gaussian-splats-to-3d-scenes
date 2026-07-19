"""Backend glue for the offline reconstruction pipeline.

Handles splat upload, a quick preview render, and running preprocess/run.py as a
background job whose stdout is streamed into an in-memory status store that the
Reconstruct page polls.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path

BACKEND = Path(__file__).parent
PREP_DIR = BACKEND / "preprocess"
WORK = BACKEND / "work"
UPLOADS = WORK / "uploads"
VENV_PY = BACKEND / "venv" / "bin" / "python"
WORK.mkdir(exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(PREP_DIR))

JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _safe(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name) or "splat"


# ---------------------------------------------------------------- upload + preview
def save_upload(filename: str, data: bytes) -> Path:
    stem = _safe(Path(filename).name)
    dest = UPLOADS / stem
    dest.write_bytes(data)
    return dest


def preview(splat_path: str) -> dict:
    """Convert the uploaded capture to a .splat the browser renders as real GPU
    gaussians, and return its URL + basic stats (no CPU renders)."""
    import numpy as np
    from loader import _load_any, clean_floaters, orient_cloud
    from ply_io import to_splat_bytes

    pos, rgb, scale, opacity = _load_any(splat_path)
    pos, rgb, scale, opacity = clean_floaters(pos, rgb, scale, opacity)
    pos, up = orient_cloud(pos)                            # level the cloud (RANSAC floor)
    mn, mx = np.percentile(pos, 2, 0), np.percentile(pos, 98, 0)
    size = mx - mn
    center = (mn + mx) / 2.0
    pos = pos - center                                    # recenter for easy framing

    out_dir = WORK / (_safe(Path(splat_path).stem) + "_prev")
    out_dir.mkdir(parents=True, exist_ok=True)
    splat_file = out_dir / "scene.splat"
    splat_file.write_bytes(to_splat_bytes(pos, rgb, scale, opacity))

    return {
        "up_axis": "XYZ"[up],
        "points": int(len(pos)),
        "size_m": [round(float(s), 2) for s in size],
        "radius": round(float(np.linalg.norm(size)) * 0.6, 2),
        "splat_url": _rel(splat_file),
    }


def _save(arr, path):
    from PIL import Image
    Image.fromarray(arr).save(path)


def _rel(p: Path) -> str:
    return "/work/" + str(Path(p).relative_to(WORK)).replace(os.sep, "/")


# ---------------------------------------------------------------- background job
STAGE_HINTS = [
    ("loading", "Loading splat"),
    ("capturing", "Capturing views"),
    ("segmenting", "Segmenting + labeling (SAM2 + VLM)"),
    ("after sliver", "Filtering detections"),
    ("unique objects", "Deduplicating in 3D"),
    ("ref ", "Generating reference images (FLUX)"),
    ("DONE", "Done"),
]


def start_job(splat_path: str, nviews: int = 12, use_flux: bool = True) -> str:
    import time
    job_id = uuid.uuid4().hex[:12]
    # unique per run: <input filename>_<epoch>  (nothing ever overwritten)
    run_name = f"{_safe(Path(splat_path).stem)}_{int(time.time())}"
    out_dir = WORK / run_name
    with _LOCK:
        JOBS[job_id] = {"stage": "queued", "log": [], "done": False,
                        "error": None, "result": None, "out": run_name}
    t = threading.Thread(target=_run, args=(job_id, splat_path, out_dir, nviews, use_flux),
                         daemon=True)
    t.start()
    return job_id


def _run(job_id, splat_path, out_dir, nviews, use_flux):
    import datetime
    os.makedirs(out_dir, exist_ok=True)
    log_path = Path(out_dir) / "pipeline_log.txt"
    logf = open(log_path, "w")
    logf.write(f"# input : {os.path.abspath(splat_path)}\n")
    logf.write(f"# run   : {out_dir.name}\n")
    logf.write(f"# start : {datetime.datetime.now().isoformat(timespec='seconds')}\n\n")
    logf.flush()
    cmd = [str(VENV_PY), "run.py", "--splat", os.path.abspath(splat_path),
           "--out", os.path.abspath(out_dir), "--nviews", str(nviews)]
    if not use_flux:
        cmd.append("--no-flux")
    try:
        proc = subprocess.Popen(cmd, cwd=str(PREP_DIR), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            logf.write(line + "\n"); logf.flush()          # tee to pipeline_log.txt
            with _LOCK:
                JOBS[job_id]["log"].append(line)
                JOBS[job_id]["log"] = JOBS[job_id]["log"][-200:]
                for key, label in STAGE_HINTS:
                    if key in line:
                        JOBS[job_id]["stage"] = label
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"pipeline exited {proc.returncode}")
        _finalize(job_id, out_dir)
    except Exception as e:  # surface any failure to the UI + log
        logf.write(f"\n# ERROR: {e}\n")
        with _LOCK:
            JOBS[job_id]["error"] = str(e)
            JOBS[job_id]["done"] = True
    finally:
        logf.write(f"\n# end   : {datetime.datetime.now().isoformat(timespec='seconds')}\n")
        logf.close()


def _finalize(job_id, out_dir):
    scene_path = Path(out_dir) / "scene.json"
    result = {"montage": None, "objects": [], "scene": None, "out_dir": str(out_dir)}
    montage = Path(out_dir) / "montage.png"
    if montage.exists():
        result["montage"] = _rel(montage)
    if scene_path.exists():
        scene = json.loads(scene_path.read_text())
        result["scene"] = _rel(scene_path)
        empty = scene.get("room", {}).get("emptyRoomImage")
        result["empty_room"] = _rel(Path(out_dir) / empty) if empty else None
        for o in scene.get("objects", []):
            ref = o.get("refImage")
            ref_url = _rel(Path(out_dir) / ref) if ref else None
            sz = o.get("size", [0, 0, 0])
            result["objects"].append({
                "id": o["id"], "label": o["label"],
                "size_m": [round(float(s), 2) for s in sz],
                "ref_url": ref_url})
        # full scene graph for the in-app importer, with the room GLB resolved to
        # a servable /work URL (object assetUrls stay /assets/obj_N.glb).
        room_asset = scene.get("room", {}).get("assetUrl")
        if room_asset and not room_asset.startswith("/assets"):
            scene["room"]["assetUrl"] = _rel(Path(out_dir) / room_asset)
        result["scene_graph"] = scene
    with _LOCK:
        JOBS[job_id]["result"] = result
        JOBS[job_id]["stage"] = "Done"
        JOBS[job_id]["done"] = True


def status(job_id: str) -> dict:
    with _LOCK:
        j = JOBS.get(job_id)
        if not j:
            return {"error": "unknown job", "done": True}
        return {"stage": j["stage"], "log": j["log"][-40:], "done": j["done"],
                "error": j["error"], "result": j["result"]}
