# Gaussian Splats → Editable 3D Scenes

**Turn a Gaussian-splat capture of a real room into a scene graph of separate, editable 3D objects — then rearrange it by typing or speaking ("put the lamp on the coffee table").**

Two parts, one repo:

1. **Reconstruction pipeline** (`staging-app/backend/preprocess/`): reads a 3DGS `.ply` / `.splat` capture, levels the floor with RANSAC, renders orbit views (RGB + depth + pose), segments objects with **SAM2**, labels them with a **vision-language model**, back-projects masks into 3D, and writes a metric, Y-up `scene.json` plus a measured `room.glb`.
2. **Spatial staging app** (`staging-app/`): a "Blender you talk to". A text LLM turns instructions into *relations* (`lamp on_top_of table`), a **deterministic resolver** turns relations into coordinates, and a local VLM checks each placement against a screenshot.

```
splat capture (.ply/.splat)
  └─► floor leveling ─► orbit renders ─► SAM2 masks ─► VLM labels ─► 3D back-projection
                                                                         │
                                                         scene.json + room.glb + object GLBs
                                                                         │
"put the plant left of the sofa" ─► LLM (relation JSON) ─► resolver (coords) ─► R3F render ─► VLM check
```

## Key design decisions

- **The LLM never outputs coordinates.** It outputs relations; a deterministic resolver (`frontend/src/resolver/resolver.ts`) computes positions from bounding boxes. This removes the main source of hallucinated placements.
- **Objects are re-pivoted to bottom-center on import**, so "on the floor" and "on a surface" become simple arithmetic.
- **One JSON scene graph is the source of truth.** Meters, Y-up, floor at y = 0, mirrored between TypeScript (`types/scene.ts`) and Pydantic (`backend/schemas.py`).
- **Runs locally.** Vision runs on Ollama (`qwen2.5vl:3b`, Apple Silicon via Metal); text can run on Ollama too, so no API key is required.

## Stack

React · TypeScript · React Three Fiber · Vite · FastAPI · SAM2 · Ollama (Qwen2.5-VL, Llama 3.1) · NVIDIA NIM · FLUX · NumPy

## Run it

Setup, endpoints and the test commands (including the 11-case resolver test suite) are in **[`staging-app/README.md`](staging-app/README.md)**. The original product spec is in [`SPEC_spatial_staging_app.md`](SPEC_spatial_staging_app.md).

## Status

Works end to end in a desktop browser. Packaging to the PICO headset emulator is deferred: it needs a full Android Studio and native-plugin toolchain ([details](staging-app/docs/PICO_EMULATOR.md)).
