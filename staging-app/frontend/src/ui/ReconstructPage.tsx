import { useEffect, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Splat, OrbitControls } from "@react-three/drei";
import { BACKEND_URL, postJSON, getJSON } from "../llm/api";

type UploadInfo = {
  splat_path: string;
  up_axis: string;
  points: number;
  size_m: number[];
  radius: number;
  splat_url: string;
};

// three.js is Y-up; rotate the splat so the capture's up-axis points up.
function upRotation(up: string): [number, number, number] {
  if (up === "Z") return [-Math.PI / 2, 0, 0];
  if (up === "X") return [0, 0, Math.PI / 2];
  return [0, 0, 0];
}

function SplatViewer({ url, up, radius }: { url: string; up: string; radius: number }) {
  const d = Math.max(radius, 2);
  return (
    <div style={{ height: 460, borderRadius: 12, overflow: "hidden", background: "#0a0c10", border: "1px solid #23262b" }}>
      <Canvas camera={{ position: [d, d * 0.7, d], fov: 50, near: 0.1, far: 1000 }}>
        <color attach="background" args={["#0a0c10"]} />
        <OrbitControls makeDefault target={[0, 0, 0]} />
        <group rotation={upRotation(up)}>
          <Splat src={url} />
        </group>
      </Canvas>
    </div>
  );
}

type ObjResult = { id: string; label: string; size_m: number[]; ref_url: string | null };
type JobResult = { montage: string | null; objects: ObjResult[]; scene: string | null; out_dir: string; empty_room: string | null; scene_graph?: unknown };
type Status = { stage: string; log: string[]; done: boolean; error: string | null; result: JobResult | null };

const abs = (p: string | null) => (p ? `${BACKEND_URL}${p}` : "");

export function ReconstructPage({ onBack, onImport }: { onBack: () => void; onImport: (scene: unknown) => void }) {
  const [uploading, setUploading] = useState(false);
  const [info, setInfo] = useState<UploadInfo | null>(null);
  const [err, setErr] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const name = file.name.toLowerCase();
    if (!name.endsWith(".ply") && !name.endsWith(".splat")) {
      setErr("Please choose a .ply or .splat file.");
      return;
    }
    setErr(""); setInfo(null); setJobId(null); setStatus(null); setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${BACKEND_URL}/preprocess/upload`, { method: "POST", body: form });
      if (!res.ok) throw new Error(await res.text());
      setInfo((await res.json()) as UploadInfo);
    } catch (e) {
      setErr(String(e));
    } finally {
      setUploading(false);
    }
  }

  async function generate() {
    if (!info) return;
    setErr("");
    try {
      const { job_id } = await postJSON<{ job_id: string }>("/preprocess", {
        splat_path: info.splat_path,
      });
      setJobId(job_id);
    } catch (e) {
      setErr(String(e));
    }
  }

  // poll status
  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    const tick = async () => {
      try {
        const s = await getJSON<Status>(`/preprocess/status/${jobId}`);
        if (!alive) return;
        setStatus(s);
        if (!s.done) setTimeout(tick, 1500);
      } catch {
        if (alive) setTimeout(tick, 2500);
      }
    };
    tick();
    return () => { alive = false; };
  }, [jobId]);

  const running = !!jobId && !(status?.done);

  return (
    <div style={{ minHeight: "100vh", background: "#0d0f12", color: "#e8eaed", padding: "24px 32px", overflowY: "auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20 }}>
        <button className="ghost" onClick={onBack}>← Back to editor</button>
        <h1 style={{ margin: 0, fontSize: 22 }}>Reconstruct from a 3D splat</h1>
      </div>
      <p style={{ color: "#9aa0a6", maxWidth: 720, marginTop: 0 }}>
        Import a Gaussian-splat capture (<code>.ply</code> or <code>.splat</code>). Preview it, then
        run the pipeline: it photographs the room, segments objects (SAM2 + vision LLM),
        measures each in meters, and generates a Tripo-ready reference image per object.
      </p>

      {/* upload */}
      <input ref={fileRef} type="file" accept=".ply,.splat" style={{ display: "none" }} onChange={onFile} />
      <button
        onClick={() => fileRef.current?.click()}
        disabled={uploading || running}
        style={{ background: "#1e88e5", color: "#fff", border: 0, padding: "10px 18px", borderRadius: 8, cursor: "pointer", fontSize: 14 }}
      >
        {uploading ? "Reading splat…" : info ? "Choose a different file" : "＋ Choose splat file"}
      </button>
      {err && <div style={{ color: "#ff6b6b", marginTop: 12 }}>{err}</div>}

      {/* preview */}
      {info && (
        <div style={{ marginTop: 24 }}>
          <div style={{ color: "#9aa0a6", marginBottom: 8, fontSize: 13 }}>
            {info.points.toLocaleString()} points · up-axis {info.up_axis} · size{" "}
            {info.size_m.join(" × ")} m · <span style={{ color: "#7fd17f" }}>drag to orbit</span>
          </div>
          <SplatViewer url={abs(info.splat_url)} up={info.up_axis} radius={info.radius} />
          <button
            onClick={generate}
            disabled={running}
            style={{ marginTop: 18, background: running ? "#2e7d32aa" : "#22c55e", color: "#06210f", fontWeight: 700, border: 0, padding: "12px 22px", borderRadius: 10, cursor: running ? "default" : "pointer", fontSize: 15 }}
          >
            {running ? "Generating…" : "⚡ Generate objects"}
          </button>
        </div>
      )}

      {/* progress */}
      {status && (
        <div style={{ marginTop: 24 }}>
          <div style={{ fontSize: 15, marginBottom: 8 }}>
            {status.error ? <span style={{ color: "#ff6b6b" }}>Failed: {status.error}</span>
              : <><b>{status.stage}</b>{running && " …"}</>}
          </div>
          {running && (
            <pre style={{ background: "#000", color: "#7fd17f", padding: 12, borderRadius: 8, maxHeight: 180, overflow: "auto", fontSize: 12 }}>
              {status.log.slice(-14).join("\n")}
            </pre>
          )}
        </div>
      )}

      {/* results */}
      {status?.result && (
        <div style={{ marginTop: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
            <h2 style={{ fontSize: 18, margin: 0 }}>Reconstructed objects ({status.result.objects.length})</h2>
            {status.result.scene_graph != null && (
              <button
                onClick={() => onImport(status.result!.scene_graph)}
                style={{ background: "#22c55e", color: "#06210f", fontWeight: 700, border: 0, padding: "9px 16px", borderRadius: 8, cursor: "pointer" }}
              >
                Open in editor →
              </button>
            )}
          </div>
          <div style={{ color: "#9aa0a6", fontSize: 12, margin: "6px 0 12px" }}>
            Generate GLBs from the reference images with Tripo, drop them in <code>backend/assets/</code> as <code>obj_1.glb …</code>, then "Open in editor" places them at their measured positions and sizes.
          </div>
          <div style={{ color: "#9aa0a6", fontSize: 12, marginBottom: 12 }}>
            Output written to <code>{status.result.out_dir}</code> (01_views · 02_sam · 03_crops · 04_refs · montage.png · scene.json)
          </div>
          {status.result.empty_room && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Empty room (objects removed)</div>
              <img src={abs(status.result.empty_room)} alt="empty room"
                style={{ maxWidth: 360, borderRadius: 10, border: "1px solid #23262b", background: "#fff" }} />
            </div>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(160px,1fr))", gap: 12 }}>
            {status.result.objects.map((o) => (
              <div key={o.id} style={{ background: "#15181d", borderRadius: 10, padding: 8, border: "1px solid #23262b" }}>
                {o.ref_url
                  ? <img src={abs(o.ref_url)} alt={o.label} style={{ width: "100%", borderRadius: 6, background: "#fff" }} />
                  : <div style={{ height: 120, background: "#222", borderRadius: 6 }} />}
                <div style={{ marginTop: 6, fontWeight: 600 }}>{o.label}</div>
                <div style={{ color: "#9aa0a6", fontSize: 12 }}>{o.size_m.join(" × ")} m</div>
              </div>
            ))}
          </div>
          {status.result.montage && (
            <div style={{ marginTop: 24 }}>
              <h3 style={{ fontSize: 16 }}>Pipeline montage</h3>
              <img src={abs(status.result.montage)} alt="montage"
                style={{ maxWidth: "100%", borderRadius: 10, border: "1px solid #23262b" }} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
