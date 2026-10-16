# Spatial Staging — a Blender you talk to

Import a 3D room and objects, then place/scale/edit them with **text or voice**.
A text LLM turns instructions into structured placement commands; a deterministic
resolver turns commands into transforms; a local vision model validates that each
placement looks correct. A single JSON scene graph is the source of truth.

Built from `SPEC_spatial_staging_app.md`. Runs in a desktop browser during
development and packages to the **PICO emulator** via WebSpatial (see
[`docs/PICO_EMULATOR.md`](docs/PICO_EMULATOR.md)).

```
frontend/   Vite + React + TypeScript + React Three Fiber  (renderer, resolver, UI)
backend/    FastAPI thin AI proxy  (text LLM, vision LLM, scene persistence, assets)
```

---

## Prerequisites

- **Node 18+** and **npm** (tested on Node 26 / npm 11)
- **Python 3.9+** (tested on 3.9; 3.11+ also fine)
- **Ollama** for the local vision model — `brew install ollama`
- A **text-LLM API key** (NVIDIA NIM or HF) — pasted into `backend/.env`
  - _Or_ run text locally too: `ollama pull llama3.1:8b` and point `TEXT_LLM_*` at Ollama (see below).

vLLM (from the original spec) needs a CUDA GPU and **cannot run on macOS**, so we use
Ollama's OpenAI-compatible endpoint for the vision model. Same interface, one URL change.

---

## Quick start (browser)

### 1. Backend

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/pip install trimesh scipy          # only needed to (re)generate demo assets
./venv/bin/python make_assets.py              # writes 7 demo GLBs into assets/
cp .env.example .env                           # then paste your TEXT_LLM_API_KEY
./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. Vision model (Ollama)

```bash
brew services start ollama        # or: ollama serve
ollama pull qwen2.5vl:3b          # ~3 GB, runs on Apple Silicon via Metal
```

### 3. Frontend

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev                        # http://localhost:5173
```

Open http://localhost:5173. The room loads automatically; use the **Asset library**
to add objects, then drive edits from the **command bar**:

- `put the lamp on the coffee table`
- `move the sofa against the wall`
- `place the plant left of the sofa`
- `remove the chair`
- `make the sofa bigger` / `scale the lamp 1.2`

Voice (the mic button) uses the Web Speech API — **Chromium only**; the text box is the primary path.

---

## Running text locally (no API key)

Edit `backend/.env`:

```
TEXT_LLM_BASE_URL=http://localhost:11434/v1
TEXT_LLM_API_KEY=ollama
TEXT_LLM_MODEL=llama3.1:8b
```

then `ollama pull llama3.1:8b`. Everything else is unchanged.

---

## How it works (the important design decisions)

1. **The room is an immutable background layer** — objects are composited into the
   same Three.js scene/coordinate frame, never fused into the room mesh.
2. **The LLM never outputs coordinates** — it outputs *relations* (`lamp, on_top_of, table`).
   The deterministic resolver (`src/resolver/resolver.ts`) computes coordinates from
   bounding boxes. This is the single most important correctness decision.
3. **Every object is re-pivoted to bottom-center** on import, so "on the floor" and
   "on a surface" are trivial arithmetic (`src/three/loadObject.ts`).
4. **World units are meters, Y-up, floor at y=0.** Everything normalizes to this.
5. **No hand-manipulation** — all edits go through the language pipeline.

Data model: `frontend/src/types/scene.ts` (mirrored in `backend/schemas.py`).

---

## Verify it works

```bash
# Backend endpoints
curl -s localhost:8000/health
curl -s localhost:8000/assets

# Deterministic resolver (11 checks: on_top_of, on_floor, against_wall, left_of, collision guard, …)
cd frontend && npx tsx test/resolver.test.mts

# Full typecheck + production build
npx tsc -b && npx vite build
```

---

## PICO emulator

**Currently demoing in the desktop browser** (works end-to-end — see Quick start
above). The PICO emulator turned out to require a full Android Studio + native
plugin toolchain rather than a standalone app; see
[`docs/PICO_EMULATOR.md`](docs/PICO_EMULATOR.md) for exactly what that involves
and why it's deferred, plus the visionOS simulator path (`npm run spatial:run`,
needs Xcode) as a lighter-weight alternative.

---

## Endpoints

| Method | Path                  | Purpose                                    |
| ------ | --------------------- | ------------------------------------------ |
| POST   | `/parse-command`      | user text → one structured command JSON    |
| POST   | `/validate-placement` | screenshot + relation → pass/fail + reason |
| GET    | `/assets`             | list GLBs in `assets/`                     |
| GET    | `/assets/*.glb`       | static asset serving                       |
| POST   | `/scene/save`         | write scene graph JSON to `scenes/`        |
| GET    | `/scene/load?name=`   | read scene graph JSON                       |
| GET    | `/health`             | liveness                                    |
