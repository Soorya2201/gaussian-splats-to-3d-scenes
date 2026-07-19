# Running in the PICO emulator (and visionOS simulator)

This app is a normal React web app; **WebSpatial is the packaging/deploy layer.**
Status as of the last setup attempt (2026-07-18): the desktop browser demo works
end-to-end today. The PICO emulator path was investigated live and turned out to
be a heavier lift than expected — see **Path A** below for exactly what it
requires and why we deferred it.

1. **Plain browser** — desktop Chrome/Chromium. **Works today**, no extra tooling.
2. **PICO OS 6 emulator** — requires Android Studio + a native plugin. Deferred
   (see Path A for the real steps if you want to pick this back up).
3. **visionOS simulator** — if you're on a Mac with Xcode, `npm run spatial:run`
   packages the app and launches it in the Apple Vision Pro simulator. Not yet
   tried on this machine (no Xcode confirmed).

---

## What's already configured (works regardless of which path you pick)

- `frontend/vite.config.ts` sets `server.host = true` so the dev server is
  reachable from other devices/emulators on the network, not just `localhost`.
- `frontend/index.html` links a Web App Manifest (`public/app.webmanifest`) — the
  minimal PWA setup WebSpatial needs.
- `@webspatial/react-sdk`, `@webspatial/core-sdk`, and `@webspatial/builder` are
  installed. The 3D scene renders inside a WebGL `<canvas>`, so it does not depend
  on the spatial JSX transform — the app is expected to run identically as a 2D
  web page inside any XR-device browser and as a spatialized app.
- Backend CORS already allow-lists `10.0.2.2` and LAN-range origins in
  `backend/main.py`, in case Path A is resumed later.

---

## Run it now (Path 0 — what actually works today)

```bash
# terminal 1 — backend
cd backend && ./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
# terminal 2 — vision model
brew services start ollama   # (or: ollama serve)
# terminal 3 — frontend
cd frontend && npm run dev
```

Open **http://localhost:5173**. Everything — room render, asset library, resolver,
text commands, vision validation, save/load — works in a plain Chrome tab.

---

## Path A — PICO OS 6 emulator (investigated, deferred — here's the real path)

**Correcting an earlier assumption:** the PICO Emulator is *not* a standalone
desktop app you download and open to get a "PICO Browser" window. It's installed
**through Android Studio**, the same way you'd add any Android Virtual Device.
Confirmed from PICO's own "Install PICO Emulator" doc
(https://developer.picoxr.com/document/spatial-toolkit/install-pico-emulator/):

### What it actually requires

1. **Android Studio** installed (not present on this machine as of last check —
   `brew install --cask android-studio` or download from
   https://developer.android.com/studio).
2. **PICO Spatial Plugin** installed inside Android Studio (separate PICO doc,
   GUI-only install via the IDE's plugin marketplace/settings).
3. In Android Studio: **Settings → Languages & Frameworks → PICO Spatial Tools**,
   check **Spatial Editor** under a PICO OS 6 version, click OK. This is what
   actually downloads the emulator binary, to the path set by "PICO Spatial Tools
   Location."
4. **Open a spatial project** in Android Studio (a native Kotlin/Android PICO
   Spatial SDK project — not this repo, which is a plain web app).
5. In that project's **Device Manager** (Android Studio's own AVD manager, Tools
   menu), click **+ → Create PICO Emulator**, then launch it with the play button
   — same flow as spinning up any Android emulator.

### Hardware check (already confirmed on this Mac — you clear all four)

| Requirement | Needed | This machine |
|---|---|---|
| macOS | 14.0+ | 26.3 ✓ |
| Chip | Apple Silicon (M1 Pro+), Intel unsupported | M4 ✓ |
| RAM | 16 GB | 16 GB ✓ (at minimum, no headroom) |
| Free disk | 32 GB | 54 GB ✓ |

### Why this was deferred

The workflow above is built for **native Kotlin/Android spatial apps**, not
web apps — it wasn't clear the resulting AVD-style emulator would even cleanly
load a plain React site the way a real headset's PICO Browser would, and getting
there requires installing the full Android Studio toolchain plus a plugin whose
install/configure steps are GUI-only (can't be scripted). Given the hackathon
timeline, decided to demo in the browser instead and revisit if time allows.

### If you pick this back up later

Once the emulator is running from Android Studio's Device Manager, the app-facing
steps are unchanged from the original plan:

```bash
# keep backend + frontend + ollama running (see "Run it now" above)
```

Then in whatever browser is available inside that emulator instance, navigate to:

```
http://10.0.2.2:5173/
```

If it loads the page but commands/assets fail, switch the frontend's backend URL
and restart Vite:

```bash
cd frontend
echo "VITE_BACKEND_URL=http://10.0.2.2:8000" > .env
npm run dev
```

(Backend CORS already allows this origin — no backend change needed.)

### On a physical PICO headset (same Wi‑Fi) — untested but should work the same way

Use the host's LAN address instead of the loopback alias — e.g.
`http://192.168.1.130:5173/` (run `ipconfig getifaddr en0` to find yours), and set
`VITE_BACKEND_URL` to the matching `http://<LAN-IP>:8000`.

---

## Path B — visionOS simulator (Mac, untested here — needs Xcode)

If you have **Xcode + the visionOS simulator** installed:

```bash
cd frontend
npm run dev            # keep the dev server running (terminal 1)
npm run spatial:run    # terminal 2: webspatial-builder run --base="http://localhost:5173/"
```

`webspatial-builder` wraps the dev URL in a visionOS App Shell and launches it in
the simulator. First run may prompt for `@webspatial/platform-visionos` (already
in devDependencies) and Xcode signing — accept the defaults.

Production build for distribution: `npm run spatial:build`.

---

## Troubleshooting

| Symptom                                   | Fix                                                                             |
| ----------------------------------------- | ------------------------------------------------------------------------------ |
| Emulator/device browser can't reach the app | Confirm `server.host` is true and the dev server prints a `Network:` URL.     |
| App loads but assets/commands fail        | Set `VITE_BACKEND_URL` to the reachable host address, restart Vite.             |
| CORS error in the emulator/device console | Backend already allows `10.0.2.2` / LAN origins; restart the backend after edits.|
| Validation screenshots are blank          | Ensure the canvas keeps `preserveDrawingBuffer: true` (set in `SceneCanvas.tsx`).|
| Voice button disabled                     | Web Speech API is Chromium-only; use the text box (the primary path).           |
