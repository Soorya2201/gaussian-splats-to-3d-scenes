import { useEffect, useRef, useState } from "react";
import { SceneCanvas } from "./three/SceneCanvas";
import { AssetPanel } from "./ui/AssetPanel";
import { CommandBar } from "./ui/CommandBar";
import { useSceneStore } from "./store/sceneStore";
import {
  listAssets,
  saveScene,
  loadScene,
  listScenes,
  deleteScene,
  uploadAsset,
  type AssetEntry,
} from "./llm/scene";
import { loadObject } from "./three/loadObject";
import { exportSceneToGLB } from "./three/exportGLB";

// Guards the ?demo=1 bootstrap against React StrictMode's double effect in dev.
let demoRan = false;

function nextFrame(): Promise<void> {
  return new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
}

export function App() {
  const [roomUrl, setRoomUrl] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [sceneName, setSceneName] = useState("demo");
  const [savedScenes, setSavedScenes] = useState<string[]>([]);
  const [exporting, setExporting] = useState(false);
  const [importingRoom, setImportingRoom] = useState(false);
  const [roomAssets, setRoomAssets] = useState<AssetEntry[]>([]);
  const roomFileInputRef = useRef<HTMLInputElement>(null);
  const snapshot = useSceneStore((s) => s.snapshot);
  const loadGraph = useSceneStore((s) => s.loadGraph);
  const clearObjects = useSceneStore((s) => s.clearObjects);

  function refreshSceneList() {
    listScenes()
      .then(setSavedScenes)
      .catch(() => {});
  }

  function refreshRoomAssets() {
    listAssets()
      .then(setRoomAssets)
      .catch(() => {});
  }

  // Switches the active room/environment. Object positions were computed
  // against the OLD room's bounds, so a room switch starts the workspace
  // fresh — same reasoning as loading a different scene.
  function switchRoom(url: string, label: string) {
    clearObjects();
    setSelectedId(null);
    setRoomUrl(url);
    setSceneName("");
    setMsg(`Room switched to "${label}". Placed objects were cleared.`);
  }

  useEffect(() => {
    refreshSceneList();
    refreshRoomAssets();
  }, []);

  // Bootstrap: find a room GLB (label contains "room") and use it as background.
  useEffect(() => {
    listAssets()
      .then(async (assets) => {
        const room = assets.find((a) => /room/i.test(a.label));
        if (room) setRoomUrl(room.url);

        // ?demo=1 — self-contained demo (no LLM): add a table + lamp and place
        // the lamp on the table via the resolver. Proves loadObject + render +
        // resolver end-to-end.
        if (new URLSearchParams(location.search).get("demo") === "1" && !demoRan) {
          demoRan = true;
          const store = useSceneStore.getState();
          const table = assets.find((a) => /coffee table|table/i.test(a.label));
          const lamp = assets.find((a) => /lamp/i.test(a.label));
          if (table) {
            const t = await loadObject(table.url, "coffee table", store.room);
            store.addObject(t.sceneObject);
          }
          if (lamp) {
            const l = await loadObject(lamp.url, "lamp", store.room);
            store.addObject(l.sceneObject);
            store.placeRelation("lamp", "on_top_of", "coffee table");
          }
        }
      })
      .catch(() => {});
  }, []);

  async function doSave() {
    const name = sceneName.trim();
    if (!name) {
      setMsg("Give the scene a name first.");
      return;
    }
    try {
      await saveScene(name, snapshot());
      setMsg(`Saved as "${name}".`);
      refreshSceneList();
    } catch (e) {
      setMsg(String(e));
    }
  }
  async function doLoad(name: string) {
    if (!name) return;
    try {
      const g = await loadScene(name);
      loadGraph(g);
      if (g.room) setRoomUrl(g.room.assetUrl);
      setSceneName(name);
      setSelectedId(null);
      setMsg(`Loaded "${name}".`);
    } catch (e) {
      setMsg(String(e));
    }
  }
  function doExportJSON() {
    const blob = new Blob([JSON.stringify(snapshot(), null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${sceneName || "scene"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  async function doExportGLB() {
    setExporting(true);
    setSelectedId(null); // drop the selection wireframe helper before capturing
    await nextFrame();
    try {
      await exportSceneToGLB(`${sceneName || "scene"}.glb`);
      setMsg("Exported scene as a single .glb.");
    } catch (e) {
      setMsg(String(e));
    } finally {
      setExporting(false);
    }
  }
  function doNewScene() {
    clearObjects();
    setSelectedId(null);
    setSceneName("");
    setMsg("Cleared placed objects — the room/environment is unchanged. Name it and Save to keep this scene.");
  }
  async function handleRoomFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".glb")) {
      setMsg("Only .glb files are supported.");
      return;
    }
    setImportingRoom(true);
    try {
      const asset = await uploadAsset(file);
      refreshRoomAssets();
      switchRoom(asset.url, asset.label);
    } catch (err) {
      setMsg(String(err));
    } finally {
      setImportingRoom(false);
    }
  }
  async function doDelete() {
    const name = sceneName.trim();
    if (!name) {
      setMsg("Pick or type a scene name to delete.");
      return;
    }
    if (!confirm(`Delete saved scene "${name}"? This can't be undone.`)) return;
    try {
      await deleteScene(name);
      refreshSceneList();
      setMsg(`Deleted "${name}".`);
    } catch (e) {
      setMsg(String(e));
    }
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          Spatial Staging
          <small>a Blender you talk to, not click</small>
        </div>

        <AssetPanel onSelect={setSelectedId} selectedId={selectedId} />

        <div className="section-title">Room (environment)</div>
        <div className="row wrap" style={{ gap: 6, marginBottom: 6 }}>
          <select
            className="input"
            style={{ flex: 1, fontSize: 13, padding: "7px 10px" }}
            value={roomUrl ?? ""}
            onChange={(e) => {
              const a = roomAssets.find((x) => x.url === e.target.value);
              if (a) switchRoom(a.url, a.label);
            }}
          >
            <option value="" disabled>
              Switch room…
            </option>
            {roomAssets.map((a) => (
              <option key={a.url} value={a.url}>
                {a.label}
              </option>
            ))}
          </select>
        </div>
        <input
          ref={roomFileInputRef}
          type="file"
          accept=".glb"
          style={{ display: "none" }}
          onChange={handleRoomFileChosen}
        />
        <div className="row wrap" style={{ gap: 6, marginBottom: 6 }}>
          <button
            className="ghost"
            style={{ width: "100%" }}
            disabled={importingRoom}
            onClick={() => roomFileInputRef.current?.click()}
          >
            {importingRoom ? "Importing…" : "+ Import a new room (.glb)"}
          </button>
        </div>

        <div className="section-title">Layout (saved object placements)</div>
        <input
          className="input"
          style={{ marginBottom: 6, fontSize: 13, padding: "7px 10px" }}
          placeholder="layout name"
          value={sceneName}
          onChange={(e) => setSceneName(e.target.value)}
        />
        <div className="row wrap" style={{ gap: 6, marginBottom: 6 }}>
          <select
            className="input"
            style={{ flex: 1, fontSize: 13, padding: "7px 10px" }}
            value=""
            onChange={(e) => e.target.value && doLoad(e.target.value)}
          >
            <option value="" disabled>
              {savedScenes.length ? "Load a saved layout…" : "No saved layouts yet"}
            </option>
            {savedScenes.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button className="ghost" onClick={doDelete} title="Delete the named layout">
            Delete
          </button>
        </div>
        <div className="row wrap" style={{ gap: 6, marginBottom: 6 }}>
          <button className="ghost" style={{ width: "100%" }} onClick={doNewScene}>
            Clear placed objects (keeps current room)
          </button>
        </div>
        <div className="row wrap" style={{ gap: 6 }}>
          <button onClick={doSave}>Save</button>
          <button onClick={doExportJSON}>Export JSON</button>
          <button onClick={doExportGLB} disabled={exporting}>
            {exporting ? "Exporting…" : "Export GLB"}
          </button>
        </div>
        {msg && <div className="status">{msg}</div>}
      </aside>

      <main className="stage">
        <SceneCanvas roomUrl={roomUrl} selectedId={selectedId} />
        <div className="overlay-hint">
          Drag to orbit · scroll to zoom. Edits go through the command bar below.
        </div>
      </main>

      <CommandBar />
    </div>
  );
}
