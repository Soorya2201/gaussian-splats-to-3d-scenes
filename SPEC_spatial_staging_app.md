# Implementation Spec: Language-Editable Spatial Staging App

**Target runtime:** WebSpatial app running in the PICO emulator (also runs in a desktop browser during development).
**One-line goal:** Import a 3D room (environment) plus 3D objects, and let a user place/scale/edit those objects inside the room using text or voice. A text LLM turns instructions into structured placement commands; a deterministic resolver turns commands into transforms; a local vision model validates that each placement looks correct. A single JSON scene graph is the source of truth.

This document is written to be handed directly to a coding agent. Build it in the milestone order in Section 15. Do not skip the coordinate-system conventions (Section 5) or the pitfalls checklist (Section 14) — most bugs in this kind of app come from those two sections.

---

## 1. Core design decisions (read first)

These are deliberate and should not be "improved" during implementation without discussion:

1. **The room is an immutable background layer.** We do NOT insert objects into the room's Gaussian-splat/point-cloud representation. We render the room (GLB or splat) and composite ordinary GLB meshes into the *same Three.js scene and coordinate frame*. This is standard and reliable; fusing meshes into a splat is a research-grade problem and is out of scope.
2. **We never let the LLM output raw coordinates.** The LLM outputs *relations* ("lamp, on_top_of, table"). A deterministic resolver computes coordinates from bounding boxes. This is the single most important correctness decision — LLMs are unreliable at 3D coordinate math and reliable at structured relation extraction.
3. **Every imported object is re-pivoted to bottom-center** (origin at horizontal center, vertical bottom of its bounding box). This makes "place on floor" and "place on surface" trivial arithmetic and eliminates a whole class of floating/sinking bugs.
4. **All world units are meters, Y-up, floor plane at y = 0.** Everything is normalized to this on import.
5. **The user never hand-manipulates meshes.** The app is view-only for direct manipulation; all edits go through the language pipeline. (This is the product thesis — "a Blender you talk to, not click.")

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│  FRONTEND  (React + React Three Fiber, runs in PICO      │
│            emulator via WebSpatial, and in browser)      │
│                                                          │
│  • Renders room + objects from the Scene Graph           │
│  • Text input box + voice button (Web Speech API)        │
│  • Computes bounding boxes, re-pivots objects            │
│  • RESOLVER: relation -> transform (deterministic TS)    │
│  • Captures canvas screenshots for validation            │
│  • Holds Scene Graph in React state (source of truth)    │
└───────────────┬──────────────────────────┬───────────────┘
                │ POST /parse-command       │ POST /validate-placement
                │ (user text -> command)    │ (screenshot -> pass/fail)
                ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│  BACKEND  (Python FastAPI — thin AI proxy only)          │
│                                                          │
│  • /parse-command  -> calls TEXT LLM (remote API)        │
│  • /validate-placement -> calls VISION model (local vLLM)│
│  • /scene/save, /scene/load  (write/read scene JSON)     │
│  • Serves /assets/*.glb                                  │
└───────────────┬──────────────────────────┬───────────────┘
                │                          │
                ▼                          ▼
        TEXT LLM (remote)          VISION LLM (local vLLM)
   NVIDIA NIM / HF Inference        Qwen2.5-VL-3B-Instruct
   (OpenAI-compatible endpoint)     (OpenAI-compatible endpoint)
```

**Why this split:** all secrets (API keys) and the GPU-bound vision model live in the backend. All geometry, state, and rendering live in the frontend where Three.js already provides the math. Each side is independently testable.

---

## 3. Tech stack and exact dependencies

**Frontend** (Vite + React + TypeScript):
- `react`, `react-dom`
- `three`
- `@react-three/fiber` — React renderer for Three.js
- `@react-three/drei` — helpers incl. `useGLTF`, `OrbitControls`, `Bounds`, and `<Splat />` for Gaussian splat rooms
- `zustand` — lightweight global store for the scene graph (avoids prop-drilling; simpler than Redux)
- WebSpatial SDK/CLI — use the project template from the hackathon Launch Pad. Treat WebSpatial as the packaging/deploy layer; the app itself is a normal React app. Develop in the browser, deploy to the emulator.

**Backend** (Python 3.11+):
- `fastapi`, `uvicorn[standard]`
- `openai` (used as a generic OpenAI-compatible client for BOTH the text API and the local vLLM endpoint)
- `python-multipart`, `pydantic`
- `pillow` (image handling for validation screenshots)

**Models:**
- **Text (remote API):** any OpenAI-compatible chat model. Recommended: `meta/llama-3.1-8b-instruct` via NVIDIA NIM, or a 7B on HF Inference. 7–8B is plenty for structured extraction. Configured via env vars (Section 12).
- **Vision (local, vLLM):** `Qwen/Qwen2.5-VL-3B-Instruct`. Launch command in Section 11. Fallback if vLLM setup fights you: Ollama `qwen2.5vl:3b` (same OpenAI-compatible interface, change base URL only).

---

## 4. Repository structure

```
staging-app/
  frontend/
    src/
      main.tsx
      App.tsx
      store/sceneStore.ts          # zustand scene graph store
      types/scene.ts               # TypeScript scene graph types (Section 5)
      three/
        Room.tsx                   # renders GLB or splat room
        SceneObject.tsx            # renders one placed object
        SceneCanvas.tsx            # R3F <Canvas>, screenshot capture
        loadObject.ts              # GLB load + re-pivot + bbox + scale-normalize
      resolver/
        resolver.ts                # relation -> transform (Section 8)
        scaleTable.ts              # category -> target real-world height
      llm/
        parseCommand.ts            # calls backend /parse-command
        validate.ts                # screenshot + calls backend /validate-placement
      voice/useSpeech.ts           # Web Speech API hook
      ui/
        CommandBar.tsx             # text box + voice button + status
        AssetPanel.tsx             # asset library / import
        VerifyBadges.tsx           # pass/flagged indicators
    index.html
    vite.config.ts
    package.json
  backend/
    main.py                        # FastAPI app + endpoints
    llm_text.py                    # text LLM client + prompt
    llm_vision.py                  # vision LLM client + prompt
    schemas.py                     # pydantic request/response models
    scene_store.py                 # save/load scene JSON to disk
    assets/                        # room + object GLBs (served statically)
    scenes/                        # saved scene graph JSON files
    .env                           # model endpoints + keys (Section 12)
  README.md
```

---

## 5. Core data model — the Scene Graph (single source of truth)

Define in `frontend/src/types/scene.ts`. The backend mirrors these as pydantic models.

```typescript
export type Vec3 = [number, number, number];

export type RelationType =
  | "on_floor"
  | "on_top_of"
  | "against_wall"
  | "left_of"
  | "right_of"
  | "in_front_of"
  | "behind"
  | "near"
  | "center_of_room";

export interface BBox {
  min: Vec3;   // world-space axis-aligned box, AFTER transform
  max: Vec3;
  size: Vec3;  // max - min
}

export interface SceneObject {
  id: string;                 // stable uuid, generated on add
  label: string;              // "lamp", "sofa" — used by the LLM to refer to it
  assetUrl: string;           // /assets/xxx.glb
  transform: {
    position: Vec3;           // world meters, Y-up. This is the BOTTOM-CENTER pivot point.
    rotationY: number;        // yaw in radians (we only expose yaw for simplicity)
    scale: number;            // uniform scale multiplier applied AFTER normalization
  };
  rawSize: Vec3;              // bounding-box size of the loaded GLB at scale=1 (for scale calc)
  targetHeight: number;      // desired real-world height in meters (from scaleTable or LLM)
  relation?: {
    type: RelationType;
    target: string;          // another object's label, or "floor" / "wall" / "room"
    align?: "center" | "left" | "right";
    offset?: number;         // extra meters of gap, default from resolver
  };
  worldBBox?: BBox;          // recomputed after every transform; used by resolver
  verified: "pending" | "pass" | "flagged";
  validationNote?: string;
}

export interface RoomScene {
  id: string;
  assetUrl: string;
  kind: "glb" | "splat";
  floorY: number;            // world Y of floor, normalized to 0 on import
  bounds: BBox;              // room extent in world meters
}

export interface SceneGraph {
  room: RoomScene | null;
  objects: SceneObject[];
  version: number;           // increment on every mutation (for React re-render + undo later)
}
```

**Rule:** the resolver and renderer both read `worldBBox`. Recompute `worldBBox` immediately after any change to `transform`. Never let it go stale.

---

## 6. Coordinate system conventions (do not violate)

- World is **meters, Y-up, right-handed** (Three.js default).
- **Floor is y = 0.** On room import, measure the room's AABB, then translate the room so its lowest point sits at y = 0. Set `room.floorY = 0`.
- **Object pivot is bottom-center:** after loading a GLB, translate its geometry so the origin is at (centerX, minY, centerZ) of its bounding box. After this, `position.y = floorY` places it flush on the floor with zero math.
- **A "surface top" Y** for object `T` is `T.worldBBox.max[1]`. To put object `O` on top of `T`: `O.position = [T.center.x, T.worldBBox.max[1], T.center.z]`.
- Room "walls" for `against_wall` are the four vertical planes of `room.bounds` (min/max X and Z).

---

## 7. Loading and normalizing an object (`loadObject.ts`)

Exact sequence — order matters:

1. Load GLB with `useGLTF` / `GLTFLoader`. **Wait for full load** before measuring (use Suspense or the loader's onLoad; never measure a partially-loaded scene).
2. Compute AABB: `const box = new THREE.Box3().setFromObject(gltf.scene);`
3. Record `rawSize = box.getSize()`.
4. **Re-pivot to bottom-center:** compute `center = box.getCenter()`, then translate all child geometry by `(-center.x, -box.min.y, -center.z)` so origin is bottom-center.
5. **Scale-normalize:** look up `targetHeight` for the object's category (Section 9). Compute `scaleFactor = targetHeight / rawSize.y`. Apply as uniform scale. (For flat items like rugs, normalize by footprint/largest horizontal dimension instead — mark these in the scale table.)
6. Add to scene graph with `verified: "pending"`, `position` initially at room center on the floor.
7. Recompute `worldBBox` from the placed, scaled object.

---

## 8. The Resolver — relation to transform (`resolver.ts`)

Pure functions. Input: the object, its target (another object or the room), the current scene graph. Output: a new `position` (and optionally `rotationY`). No model calls. This is ~150 lines total.

Assume bottom-center pivots and that `worldBBox` is current. Let `O` = object being placed, `T` = target object, `R` = room. `gap` default = 0.05 m unless overridden by `relation.offset`.

- **on_floor:** `O.position = [O.position.x, R.floorY, O.position.z]` (keep current x/z, drop to floor).
- **center_of_room:** `O.position = [R.center.x, R.floorY, R.center.z]`.
- **on_top_of(T):** `O.position = [T.center.x, T.worldBBox.max.y, T.center.z]`. (Bottom-center pivot means we set y directly to the target's top.)
- **against_wall:** find the nearest wall plane to O's current position among the 4 room-bound planes. Snap the object's back face to it: if it's the +X wall, `O.position.x = R.bounds.max.x - O.halfSize.x - gap`; analogous for the other three. Set `rotationY` so the object faces into the room. Keep on floor.
- **left_of(T):** `O.position = [T.center.x - T.halfSize.x - gap - O.halfSize.x, R.floorY, T.center.z]`. (Left = negative X by convention; document this.)
- **right_of(T):** mirror of left_of (positive X).
- **in_front_of(T):** `O.position = [T.center.x, R.floorY, T.center.z + T.halfSize.z + gap + O.halfSize.z]`. (Front = +Z by convention.)
- **behind(T):** mirror of in_front_of (−Z).
- **near(T):** place O at floor level, offset from T by `(T.halfSize + O.halfSize + 0.3m)` along the axis with the most free space; simplest correct default is the +X side, then let the validator/user nudge.

After computing `position`, recompute `O.worldBBox`, then run a **collision guard**: if O's new `worldBBox` intersects any other object's `worldBBox` (except its support target), push O along the shorter overlap axis until clear, up to a small cap. This prevents interpenetration cheaply.

Provide `halfSize.x = worldBBox.size.x / 2`, etc. as helpers.

---

## 9. Scale table (`scaleTable.ts`)

A dictionary of sane real-world heights in meters. The LLM may override via `targetHeight`, but this is the fallback so nothing is ever wildly mis-sized.

```typescript
export const SCALE_TABLE: Record<string, { height: number; axis?: "y" | "footprint" }> = {
  table:   { height: 0.75 },
  desk:    { height: 0.75 },
  chair:   { height: 0.90 },
  sofa:    { height: 0.85 },
  lamp:    { height: 0.50 },
  floorlamp:{ height: 1.60 },
  plant:   { height: 0.60 },
  rug:     { height: 0.02, axis: "footprint" },
  bookshelf:{ height: 1.80 },
  bed:     { height: 0.60 },
  tv:      { height: 0.65 },
  vase:    { height: 0.30 },
  apple:   { height: 0.08 },
  default: { height: 0.50 },
};
```

Match the object label to the closest key (lowercase, substring match, else `default`).

---

## 10. Text LLM — command parser (`backend/llm_text.py` + frontend `parseCommand.ts`)

**Contract:** frontend sends the user's utterance plus the current object labels; backend returns a single structured command JSON. The LLM is told the exact schema and the closed set of relations, and to output JSON only.

**Backend endpoint** `POST /parse-command`:
Request:
```json
{ "text": "put the lamp on the coffee table",
  "objects": [{"id":"...","label":"lamp"},{"id":"...","label":"coffee table"}],
  "hasRoom": true }
```
Response (one of):
```json
{ "action": "place",
  "object": "lamp",
  "relation": "on_top_of",
  "target": "coffee table",
  "align": "center",
  "targetHeight": null }
```
```json
{ "action": "add",    "object": "plant" }
{ "action": "remove", "object": "lamp" }
{ "action": "scale",  "object": "sofa", "factor": 1.2 }
{ "action": "clear" }
{ "action": "error",  "message": "No object called 'chair' is in the scene." }
```

**System prompt (exact):**
```
You convert a user's natural-language instruction about arranging a 3D room into ONE JSON command.
Output JSON ONLY. No prose, no markdown, no code fences.

Valid actions: "place", "add", "remove", "scale", "clear", "error".
Valid relations (for "place"): on_floor, on_top_of, against_wall, left_of, right_of,
  in_front_of, behind, near, center_of_room.
Rules:
- "object" and "target" MUST be labels drawn from the provided object list (match case-insensitively).
  If the user names something not in the list, return action "error" with a helpful message.
- Never output numeric coordinates. Positions are decided by relations only.
- "align" is optional: center|left|right (default center).
- "targetHeight" is optional meters, only if the user specifies a size.

Object list: {OBJECTS}
Room present: {HAS_ROOM}

Return exactly one JSON object.
```
Few-shot examples (include 3–4 in the prompt) covering place-on-top, against-wall, remove, and an error case.

**Robustness:** after the call, extract the first `{...}` block, `json.loads` it; on failure, retry once with a "your last output was not valid JSON, return JSON only" nudge; on second failure return `{"action":"error","message":"Could not parse that."}`. Validate the parsed object against a pydantic model before returning.

Use the `openai` client pointed at `TEXT_LLM_BASE_URL` with `TEXT_LLM_MODEL`, `temperature=0`.

---

## 11. Vision LLM — placement validator (`backend/llm_vision.py` + frontend `validate.ts`)

**Launch the local model (vLLM):**
```bash
pip install vllm
vllm serve Qwen/Qwen2.5-VL-3B-Instruct \
  --port 8001 \
  --max-model-len 8192 \
  --limit-mm-per-prompt image=2
# Serves an OpenAI-compatible API at http://localhost:8001/v1
# VRAM: ~8-10 GB. If unavailable, fallback:  ollama run qwen2.5vl:3b  (base url http://localhost:11434/v1)
```

**Frontend** captures a screenshot of the current render (Section 13 for the capture mechanism) and sends it with the intended relation.

**Backend endpoint** `POST /validate-placement`:
Request:
```json
{ "image_base64": "data:image/jpeg;base64,...",
  "object": "lamp",
  "relation_phrase": "on top of",
  "target": "coffee table" }
```
Response:
```json
{ "pass": false,
  "reason": "The lamp is floating a few centimeters above the table surface.",
  "suggestion": "move_down" }
```

**Vision prompt (exact), narrow and closed-form:**
```
You are inspecting a rendered 3D scene. The user intended to place the {object}
{relation_phrase} the {target}.
Look at the image and judge ONLY these three things:
1. Contact/position: is the {object} actually {relation_phrase} the {target},
   with no visible floating gap and no interpenetration?
2. Scale: is the {object} a plausible real-world size relative to the {target}?
3. Nothing else.
Respond with JSON ONLY:
{"pass": true|false, "reason": "<one short sentence>",
 "suggestion": "move_up|move_down|move_left|move_right|scale_up|scale_down|none"}
"pass" is true ONLY if position AND scale are both correct.
```

**Retry loop (frontend, capped at 3):**
- If `pass` is false and retries remain, apply a small nudge mapped from `suggestion`:
  `move_down: y -= 0.03`, `move_up: y += 0.03`, `move_left: x -= 0.05`, `move_right: x += 0.05`,
  `scale_down: scale *= 0.9`, `scale_up: scale *= 1.1`, `none: stop`.
- Recompute `worldBBox`, re-render, re-capture, re-validate.
- After 3 tries or a `pass`, set `verified` to `"pass"` or `"flagged"` and store `validationNote`. Show the badge in the UI. Never loop unbounded.

---

## 12. Configuration (`backend/.env`)

```
# Remote text model (OpenAI-compatible: NVIDIA NIM or HF Inference)
TEXT_LLM_BASE_URL=https://integrate.api.nvidia.com/v1
TEXT_LLM_API_KEY=***paste key***
TEXT_LLM_MODEL=meta/llama-3.1-8b-instruct

# Local vision model (vLLM). No key needed for local.
VISION_BASE_URL=http://localhost:8001/v1
VISION_API_KEY=EMPTY
VISION_MODEL=Qwen/Qwen2.5-VL-3B-Instruct

# Server
FRONTEND_ORIGIN=http://localhost:5173
```
Frontend needs only the backend base URL (e.g. `VITE_BACKEND_URL=http://localhost:8000`).

---

## 13. Screenshot capture (critical detail — gets missed and silently breaks)

The R3F `<Canvas>` MUST be created with `gl={{ preserveDrawingBuffer: true }}`, otherwise `toDataURL` returns a blank image.

```tsx
// SceneCanvas.tsx
<Canvas gl={{ preserveDrawingBuffer: true }} camera={{ position: [3, 2, 4], fov: 50 }}>
  ...
</Canvas>
```
Capture function (call AFTER a frame has rendered — invalidate/render once first if using demand mode):
```tsx
function captureScreenshot(gl: THREE.WebGLRenderer): string {
  return gl.domElement.toDataURL("image/jpeg", 0.85);
}
```
Expose `gl` via `useThree()` and hoist the capture function through a ref so the validation flow can call it.

---

## 14. Pitfalls checklist (verify each before demo)

1. `preserveDrawingBuffer: true` is set, or validation screenshots are blank.
2. Room normalized so floor is exactly y = 0; objects use bottom-center pivots.
3. Bounding boxes are computed only after each GLB is fully loaded.
4. `worldBBox` is recomputed after EVERY transform change (position, scale, rotation).
5. CORS enabled on FastAPI for the Vite origin (`fastapi.middleware.cors.CORSMiddleware`, allow the frontend origin).
6. Text LLM output is JSON-extracted, validated against pydantic, with a one-shot repair retry.
7. vLLM VRAM confirmed on the demo machine; Ollama fallback path tested at least once.
8. If the room is a splat and `<Splat/>` misbehaves, fall back to a GLB room (keep one GLB room asset ready).
9. Voice uses Web Speech API — Chromium only. Always keep the text box as the primary path.
10. Validation retries are hard-capped at 3. No unbounded loops.
11. LLM references an object not in the scene → graceful `error` action, not a crash.
12. Object label matching is case-insensitive and tolerant of "coffee table" vs "table" (substring/fuzzy).
13. Only uniform scaling is applied (single `scale` float) — do not introduce non-uniform scale, it breaks the bbox assumptions.

---

## 15. Build order for the coding agent (milestones — build and TEST each before the next)

**M1 — Static render.** Vite + React + R3F app. Hardcode: load one room GLB (normalized to floor y=0) and one object GLB (bottom-center pivot, scale-normalized), placed on the floor. Define all scene-graph TypeScript types and the zustand store. *Test: object sits correctly sized on the floor inside the room, orbit controls work.*

**M2 — Asset management.** Asset panel listing GLBs from `backend/assets/` (plus optional file upload). Adding an object runs the full `loadObject` sequence and inserts it into the scene graph at room center on the floor. *Test: add 3 different objects, all correctly sized, none floating.*

**M3 — Resolver + manual buttons.** Implement `resolver.ts` and `scaleTable.ts`. Add temporary UI buttons ("lamp on_top_of table", "sofa against_wall") that call the resolver directly. *Test: each relation produces visually correct placement; collision guard separates overlapping objects.*

**M4 — Text pipeline.** FastAPI `/parse-command` wired to the text LLM. Replace the buttons with the command bar text box: utterance → command JSON → resolver → scene graph → re-render. *Test: "put the lamp on the table", "move the sofa against the wall", "remove the plant" all work; nonsense input returns a graceful error.*

**M5 — Vision validation.** vLLM up. `/validate-placement` wired. After each placement, capture screenshot → validate → show pass/flagged badge → run capped retry loop on failure. *Test: deliberately mis-scale an object and confirm the validator flags it and the retry corrects it.*

**M6 — Voice + persistence.** Web Speech API hook feeding the same command pipeline. `/scene/save` and `/scene/load` writing the scene JSON to disk. Export-scene button. *Test: full voice-driven edit; reload restores the scene.*

**M7 — WebSpatial / PICO.** Package the app with the WebSpatial template from the Launch Pad and run it in the PICO emulator. Verify the render, command bar, and validation all work in-emulator, not just the browser. *Test: complete one full edit loop inside the PICO emulator.*

---

## 16. Demo-day fallback ladder (if time runs short)

- Cut voice (M6) first — text box covers the same capability.
- Cut the vision retry loop before cutting the vision check — showing a "flagged" badge is still a strong story even without auto-correction.
- Cut the splat room to a GLB room if `<Splat/>` is unstable.
- Cut arbitrary upload; ship a curated asset library of 5–6 pre-generated Tripo GLBs (more reliable than live generation on stage).
- Absolute minimum viable demo: M1–M4 (text-driven placement of pre-loaded assets in a GLB room, running in the emulator). That alone is a coherent, judge-ready story.
