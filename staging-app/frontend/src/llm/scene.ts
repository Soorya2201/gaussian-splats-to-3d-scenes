// Scene persistence + asset listing client.
import { getJSON, postJSON, BACKEND_URL } from "./api";
import type { SceneGraph } from "../types/scene";

export interface AssetEntry {
  label: string; // derived filename label
  url: string; // /assets/xxx.glb (absolute, backend-served)
}

export async function listAssets(): Promise<AssetEntry[]> {
  const raw = await getJSON<{ assets: { name: string; file: string }[] }>("/assets");
  return raw.assets.map((a) => ({
    label: a.name,
    url: `${BACKEND_URL}/assets/${a.file}`,
  }));
}

// Uploads a user-supplied .glb. Uses FormData (not postJSON) so the browser
// sets the correct multipart boundary itself.
export async function uploadAsset(file: File): Promise<AssetEntry> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BACKEND_URL}/assets/upload`, { method: "POST", body: form });
  if (!res.ok) {
    throw new Error(`Upload failed: ${await res.text()}`);
  }
  const data = (await res.json()) as { name: string; file: string };
  return { label: data.name, url: `${BACKEND_URL}/assets/${data.file}` };
}

export async function saveScene(name: string, graph: SceneGraph): Promise<void> {
  await postJSON("/scene/save", { name, graph });
}

export async function loadScene(name: string): Promise<SceneGraph> {
  return getJSON<SceneGraph>(`/scene/load?name=${encodeURIComponent(name)}`);
}

export async function listScenes(): Promise<string[]> {
  const raw = await getJSON<{ scenes: string[] }>("/scene/list");
  return raw.scenes;
}

export async function deleteScene(name: string): Promise<void> {
  const res = await fetch(`${BACKEND_URL}/scene?name=${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error(`Delete failed: ${await res.text()}`);
  }
}
