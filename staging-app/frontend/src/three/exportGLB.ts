// Merges the live, already-transformed Three.js scene (room + every placed
// object at its current position/rotation/scale) into a single binary glTF
// (.glb) and triggers a browser download. Reuses exactly what's on screen —
// no server round-trip, no re-parsing of the source GLBs.
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";
import { getExportRoot } from "./exportBridge";

export function exportSceneToGLB(filename = "scene.glb"): Promise<void> {
  return new Promise((resolve, reject) => {
    const root = getExportRoot();
    if (!root) {
      reject(new Error("Nothing to export yet — the scene hasn't rendered."));
      return;
    }
    const exporter = new GLTFExporter();
    exporter.parse(
      root,
      (result) => {
        const buffer = result as ArrayBuffer;
        const blob = new Blob([buffer], { type: "model/gltf-binary" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename.endsWith(".glb") ? filename : `${filename}.glb`;
        a.click();
        URL.revokeObjectURL(url);
        resolve();
      },
      (error) => reject(error instanceof Error ? error : new Error(String(error))),
      { binary: true },
    );
  });
}
