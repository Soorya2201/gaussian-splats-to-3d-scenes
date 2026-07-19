// Module-level holder for the exportable Three.js group (room + placed objects,
// excluding editor-only helpers like the orbit grid or selection wireframe).
// Same registration pattern as capture.ts.
import type * as THREE from "three";

type Getter = () => THREE.Object3D | null;

let getter: Getter = () => null;

export function registerExportRoot(fn: Getter) {
  getter = fn;
}

export function getExportRoot(): THREE.Object3D | null {
  return getter();
}
