// Asset library: lists GLBs from backend/assets and adds them to the scene
// (running the full loadObject sequence). Also lists placed objects with badges.
import { useEffect, useRef, useState } from "react";
import { listAssets, uploadAsset, type AssetEntry } from "../llm/scene";
import { loadObject } from "../three/loadObject";
import { useSceneStore } from "../store/sceneStore";
import { validateAndCorrect } from "../llm/validate";
import { isValidationEnabled } from "../controller";
import { VerifyBadge } from "./VerifyBadges";

export function AssetPanel({
  onSelect,
  selectedId,
}: {
  onSelect: (id: string | null) => void;
  selectedId: string | null;
}) {
  const [assets, setAssets] = useState<AssetEntry[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const objects = useSceneStore((s) => s.objects);
  const room = useSceneStore((s) => s.room);
  const addObject = useSceneStore((s) => s.addObject);
  const removeObject = useSceneStore((s) => s.removeObject);

  function refreshAssets() {
    return listAssets()
      .then((a) => setAssets(a.filter((x) => !/room/i.test(x.label))))
      .catch((e) => setErr(String(e)));
  }

  useEffect(() => {
    void refreshAssets();
  }, []);

  async function add(a: AssetEntry) {
    try {
      const { sceneObject } = await loadObject(a.url, a.label, room);
      addObject(sceneObject);
      onSelect(sceneObject.id);
      // Same reasoning as controller.ts's addObjectByLabel: a bare Add still
      // needs its floor contact + scale checked, not just relation-driven
      // placements — otherwise it sits "pending" forever.
      if (isValidationEnabled()) {
        void validateAndCorrect(sceneObject.id, "on_floor", "the floor");
      }
    } catch (e) {
      setErr(String(e));
    }
  }

  async function handleFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file later
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".glb")) {
      setErr("Only .glb files are supported.");
      return;
    }
    setUploading(true);
    setErr(null);
    setUploadMsg(null);
    try {
      const asset = await uploadAsset(file);
      await refreshAssets();
      setUploadMsg(`Imported "${asset.label}" — click Add to place it.`);
    } catch (err) {
      setErr(String(err));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div>
      <div className="section-title">Asset library</div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".glb"
        style={{ display: "none" }}
        onChange={handleFileChosen}
      />
      <button
        className="ghost"
        style={{ width: "100%", marginBottom: 8 }}
        disabled={uploading}
        onClick={() => fileInputRef.current?.click()}
      >
        {uploading ? "Importing…" : "+ Import your own .glb"}
      </button>
      {uploadMsg && <div className="status ok">{uploadMsg}</div>}
      {err && <div className="status err">{err}</div>}
      {assets.length === 0 && !err && (
        <div className="status">No assets found in backend/assets/.</div>
      )}
      {assets.map((a) => (
        <div className="asset" key={a.url}>
          <span>{a.label}</span>
          <button onClick={() => add(a)}>Add</button>
        </div>
      ))}

      <div className="section-title">In scene ({objects.length})</div>
      <div className="objects-list">
        {objects.map((o) => (
          <div
            className="obj-row"
            key={o.id}
            onClick={() => onSelect(o.id === selectedId ? null : o.id)}
            style={{
              background: o.id === selectedId ? "var(--panel-2)" : undefined,
              cursor: "pointer",
            }}
          >
            <span>{o.label}</span>
            <span className="row" style={{ gap: 6 }}>
              <VerifyBadge state={o.verified} note={o.validationNote} />
              <button
                className="ghost"
                onClick={(e) => {
                  e.stopPropagation();
                  removeObject(o.id);
                  if (selectedId === o.id) onSelect(null);
                }}
              >
                ✕
              </button>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
