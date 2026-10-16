# Gaussian Splats to Editable 3D Scenes

**Turns a Gaussian-splat capture of a real room into a scene graph of separate, measured objects, then lets you rearrange the room by typing or speaking ("put the lamp on the coffee table").**

![Python](https://img.shields.io/badge/Python-FastAPI-009688?style=flat-square)
![TypeScript](https://img.shields.io/badge/TypeScript-React%20Three%20Fiber-3178C6?style=flat-square)
![Models](https://img.shields.io/badge/models-SAM2%20%C2%B7%20VLM%20%C2%B7%20FLUX-555?style=flat-square)

## Highlights

- **Reconstruction without a GPU renderer.** A CPU point-cloud rasterizer with a z-buffer renders orbit views of the splat. Because the pipeline owns the camera, every segmented pixel back-projects to an exact 3D world point. That makes object sizes **metric**, not guessed.
- **Reads real-world splat formats.** It handles standard 3DGS `.ply` (SH DC plus activations), PlayCanvas compressed `.ply` (bit-packed chunks), the 32-byte antimatter15 `.splat` format, and plain point clouds, with floater removal and automatic up-axis and floor detection.
- **Each model does the job it is good at.** SAM2 segments every view; detections are merged across views by 3D centroid clustering, so the same lamp seen 12 times becomes one object. A VLM names one cropped object at a time, since VLMs are strong at naming a single crop and weak at localizing objects in a whole scene. FLUX.1 renders a clean reference image per object for image-to-3D.
- **The LLM never outputs coordinates.** In the editor, a text LLM turns instructions into relations (`lamp on_top_of table`). A deterministic resolver converts relations into positions from bounding boxes, and a local vision model checks the result from a screenshot. This removes hallucinated placements by construction.
- **Runs locally.** Vision runs on Ollama (Qwen2.5-VL 3B, on Apple Silicon via Metal), and text can run on Ollama too, so no API key is required.

## Pipeline

```
splat capture (.ply / .splat)
  │  loader: format detection, floater cleaning, up-axis + floor detection
  ▼
orbit capture: CPU rasterizer → RGB + depth + camera pose per view
  ▼
SAM2 auto-masks per view ─► back-project masks to 3D ─► cluster across views (eps 0.4 m)
  ▼
per-object crop ─► VLM label ─► VLM description ─► FLUX.1 reference image
  ▼
scene.json (Y-up, metres, floor at y = 0) + measured room.glb + per-object assets
  ▼
editor: "put the plant left of the sofa"
  ─► LLM → {object, relation, target} ─► resolver → transform ─► React Three Fiber ─► VLM check
```

| Stage | Code |
|---|---|
| Splat parsing | `backend/preprocess/ply_io.py`, `splat_io.py` |
| Load, clean, orient | `backend/preprocess/loader.py` |
| Rasterize and capture | `backend/preprocess/renderer.py`, `capture.py` |
| Segment, label, measure | `backend/preprocess/segment.py`, `label.py`, `measure.py` |
| Reference images | `backend/preprocess/reference.py` |
| Relation resolver | `frontend/src/resolver/resolver.ts` (11 test cases) |
| Command parsing and validation | `frontend/src/llm/`, `backend/llm_text.py`, `backend/llm_vision.py` |

## Design decisions

- **One JSON scene graph is the source of truth**, mirrored between TypeScript (`types/scene.ts`) and Pydantic (`backend/schemas.py`).
- **The room is an immutable background layer.** Objects are composited into the same coordinate frame, never fused into the room mesh, so any object can move without re-meshing.
- **Objects are re-pivoted to bottom-center on import**, so "on the floor" and "on a surface" are simple arithmetic.
- **Graceful degradation.** If FLUX generation fails, the pipeline falls back to the masked crop instead of blocking.

## Tech stack

Python · FastAPI · NumPy · SAM2 · NVIDIA NIM (vision LLM, FLUX.1-dev) · Ollama (Qwen2.5-VL, Llama 3.1) · TypeScript · React · React Three Fiber · Vite · Web Speech API

## Run it

```bash
# reconstruction (offline CLI)
cd staging-app/backend
python -m preprocess.run --splat path/to/room.ply --out work/room --nviews 12

# editor
# see staging-app/README.md for backend, Ollama and frontend setup
```

Full setup, API endpoints and test commands are in **[`staging-app/README.md`](staging-app/README.md)**. The original product spec is [`SPEC_spatial_staging_app.md`](SPEC_spatial_staging_app.md).

## Status

Works end to end in a desktop browser. Packaging for the PICO headset emulator is deferred, because it needs a full Android Studio and native-plugin toolchain ([details](staging-app/docs/PICO_EMULATOR.md)).
