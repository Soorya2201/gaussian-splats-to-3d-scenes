"""FastAPI app — thin AI proxy + scene persistence + asset serving. Spec Section 2/4."""
from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).parent / ".env")

from llm_text import parse_command  # noqa: E402
from llm_vision import validate_placement  # noqa: E402
from schemas import (  # noqa: E402
    Command,
    ParseRequest,
    SaveRequest,
    SceneGraphModel,
    ValidateRequest,
    ValidateResponse,
)
from scene_store import delete_scene, list_scenes, load_scene, save_scene  # noqa: E402
import preprocess_api  # noqa: E402

ASSETS_DIR = Path(__file__).parent / "assets"
ASSETS_DIR.mkdir(exist_ok=True)
WORK_DIR = Path(__file__).parent / "work"
WORK_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Spatial Staging Backend")

# CORS for the Vite dev origin (and the PICO emulator origin 10.0.2.2).
_frontend = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        _frontend,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://10.0.2.2:5173",
    ],
    allow_origin_regex=r"http://(10\.0\.2\.2|localhost|127\.0\.0\.1|192\.168\.\d+\.\d+):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health() -> dict:
    return {"ok": True}


def _label_for(p: Path) -> str:
    return p.stem.replace("_", " ").replace("-", " ").strip()


@app.get("/assets")
def list_assets() -> dict:
    """List .glb files in assets/ with a human label derived from the filename."""
    items = []
    for p in sorted(ASSETS_DIR.glob("*.glb")):
        items.append({"name": _label_for(p), "file": p.name})
    return {"assets": items}


@app.post("/assets/upload")
async def upload_asset(file: UploadFile = File(...)) -> dict:
    """Accept a user-supplied .glb and drop it into assets/ so it shows up in
    the Asset Library on the next listing. Validates the binary glTF magic
    number (b"glTF") rather than trusting the filename extension alone."""
    if not file.filename or not file.filename.lower().endswith(".glb"):
        raise HTTPException(status_code=400, detail="Only .glb files are supported.")

    data = await file.read()
    if len(data) < 4 or data[:4] != b"glTF":
        raise HTTPException(
            status_code=400,
            detail="That doesn't look like a valid binary glTF (.glb) file.",
        )

    stem = re.sub(r"[^a-zA-Z0-9_-]", "_", Path(file.filename).stem) or "asset"
    dest = ASSETS_DIR / f"{stem}.glb"
    n = 1
    while dest.exists():
        dest = ASSETS_DIR / f"{stem}_{n}.glb"
        n += 1

    dest.write_bytes(data)
    return {"name": _label_for(dest), "file": dest.name}


# ---------------------------------------------------------------- reconstruction
@app.post("/preprocess/upload")
async def preprocess_upload(file: UploadFile = File(...)) -> dict:
    """Accept a .ply/.splat capture, save it, and return a quick preview render."""
    name = (file.filename or "").lower()
    if not (name.endswith(".ply") or name.endswith(".splat")):
        raise HTTPException(status_code=400, detail="Upload a .ply or .splat file.")
    data = await file.read()
    dest = preprocess_api.save_upload(file.filename, data)
    try:
        info = preprocess_api.preview(str(dest))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read splat: {e}")
    return {"splat_path": str(dest), **info}


@app.post("/preprocess")
def preprocess_start(body: dict) -> dict:
    splat_path = body.get("splat_path")
    if not splat_path or not Path(splat_path).exists():
        raise HTTPException(status_code=400, detail="Unknown splat_path.")
    job_id = preprocess_api.start_job(
        splat_path, nviews=int(body.get("nviews", 12)),
        use_flux=bool(body.get("use_flux", True)))
    return {"job_id": job_id}


@app.get("/preprocess/status/{job_id}")
def preprocess_status(job_id: str) -> dict:
    return preprocess_api.status(job_id)


@app.post("/parse-command", response_model=Command)
def post_parse_command(req: ParseRequest) -> Command:
    return parse_command(req.text, req.objects, req.hasRoom)


@app.post("/validate-placement", response_model=ValidateResponse)
def post_validate_placement(req: ValidateRequest) -> ValidateResponse:
    return validate_placement(req)


@app.post("/scene/save")
def post_scene_save(req: SaveRequest) -> dict:
    path = save_scene(req.name, req.graph)
    return {"ok": True, "path": str(path.name)}


@app.get("/scene/load", response_model=SceneGraphModel)
def get_scene_load(name: str = Query("demo")) -> SceneGraphModel:
    try:
        return load_scene(name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/scene/list")
def get_scene_list() -> dict:
    return {"scenes": list_scenes()}


@app.delete("/scene")
def delete_scene_endpoint(name: str = Query(...)) -> dict:
    try:
        delete_scene(name)
        return {"ok": True}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Registered last: a Mount captures every HTTP method for its path prefix, so if
# this were declared before the /assets and /assets/upload routes above, it would
# intercept POST /assets/upload and reject it with 405 (StaticFiles only serves
# GET/HEAD) before our route ever saw the request.
app.mount("/work", StaticFiles(directory=str(WORK_DIR)), name="work")
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
