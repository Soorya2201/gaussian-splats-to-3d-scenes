// Import an externally-authored (reconstructed) scene graph into the editor.
//
// The pipeline's scene.json gives each object a metric position + targetHeight
// but scale=1.0 and no rawSize (the GLB doesn't exist at pipeline time). This
// bridges that gap: for every object we run the proven loadObject() — which
// loads the Tripo GLB, measures it, scales it to targetHeight, and pivots to
// bottom-center — then place it at the JSON's position. Duplicates (same label,
// different ids/positions) each load independently.
import { loadObject } from "./loadObject";
import { useSceneStore } from "../store/sceneStore";
import type { RoomScene, Vec3 } from "../types/scene";

export interface ImportResult {
  loaded: number;
  skipped: string[];   // object ids whose GLB failed to load (not yet generated)
  roomUrl: string | null;
}

function resolve(url: string | null, backendUrl: string): string | null {
  if (!url) return null;
  return url.startsWith("http") ? url : backendUrl + url;
}

export async function importReconstructedScene(
  scene: any,
  backendUrl: string,
): Promise<ImportResult> {
  const store = useSceneStore.getState();
  store.clearObjects();

  const roomUrl = resolve(scene?.room?.assetUrl ?? null, backendUrl);
  const roomStub: RoomScene = {
    id: scene?.room?.id ?? "room_0",
    assetUrl: roomUrl ?? "",
    kind: "glb",
    floorY: scene?.room?.floorY ?? 0,
    bounds: scene?.room?.bounds ?? { min: [0, 0, 0], max: [1, 1, 1], size: [1, 1, 1] },
  };

  const skipped: string[] = [];
  let loaded = 0;
  for (const o of scene?.objects ?? []) {
    const url = resolve(o.assetUrl, backendUrl)!;
    try {
      const { sceneObject } = await loadObject(url, o.label, roomStub, {
        targetHeight: o.targetHeight,
        position: o.transform?.position as Vec3,
      });
      sceneObject.id = o.id ?? sceneObject.id;                 // keep pipeline id
      sceneObject.transform.rotationY = o.transform?.rotationY ?? 0;
      store.addObject(sceneObject);
      loaded++;
    } catch {
      skipped.push(o.id ?? o.label);                          // GLB not placed yet
    }
  }
  return { loaded, skipped, roomUrl };
}
