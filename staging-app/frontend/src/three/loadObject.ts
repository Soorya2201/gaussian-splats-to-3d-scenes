// Loading and normalizing an object. Spec Section 7 — order matters.
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { SceneObject, RoomScene, Vec3 } from "../types/scene";
import { computeWorldBBox } from "./geometry";
import { lookupScale } from "../resolver/scaleTable";

const loader = new GLTFLoader();

// Cache loaded+normalized THREE.Object3D by url so SceneObject.tsx can render
// the same geometry the loader measured (identical pivot/scale assumptions).
const cache = new Map<string, THREE.Object3D>();

export function getCachedObject(url: string): THREE.Object3D | undefined {
  const o = cache.get(url);
  return o ? o.clone(true) : undefined;
}

function loadGLTF(url: string): Promise<THREE.Group> {
  return new Promise((resolve, reject) => {
    loader.load(
      url,
      (gltf) => resolve(gltf.scene),
      undefined,
      (err) => reject(err),
    );
  });
}

let idCounter = 0;
function uuid(prefix: string): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${idCounter++}`;
}

export interface LoadedObject {
  sceneObject: SceneObject;
  object3d: THREE.Object3D; // normalized (bottom-center pivot), scale NOT applied
}

// Full load sequence: load -> measure -> re-pivot to bottom-center ->
// scale-normalize by category -> return SceneObject placed at room center on floor.
export async function loadObject(
  assetUrl: string,
  label: string,
  room: RoomScene | null,
  opts?: { targetHeight?: number; position?: Vec3 },
): Promise<LoadedObject> {
  // 1. Load and WAIT for full load before measuring.
  const scene = await loadGLTF(assetUrl);

  // 2. Compute AABB of the fully-loaded scene.
  const box = new THREE.Box3().setFromObject(scene);
  const size = new THREE.Vector3();
  const center = new THREE.Vector3();
  box.getSize(size);
  box.getCenter(center);

  // 3. Record rawSize.
  const rawSize: Vec3 = [size.x, size.y, size.z];

  // 4. Re-pivot to bottom-center: translate geometry by (-cx, -minY, -cz).
  scene.position.set(-center.x, -box.min.y, -center.z);
  // Bake the translation into a wrapper group so the object's own origin is
  // bottom-center regardless of how it's later positioned.
  const pivoted = new THREE.Group();
  pivoted.add(scene);
  pivoted.updateMatrixWorld(true);

  // 5. Scale-normalize by category (or explicit targetHeight).
  const entry = lookupScale(label);
  const targetHeight = opts?.targetHeight ?? entry.height;
  let scaleFactor: number;
  if (entry.axis === "footprint") {
    // flat items (rugs): normalize by largest horizontal dimension
    const footprint = Math.max(rawSize[0], rawSize[2]) || 1;
    // interpret targetHeight as desired footprint here
    scaleFactor = (targetHeight || entry.height) / footprint;
  } else {
    scaleFactor = targetHeight / (rawSize[1] || 1);
  }

  cache.set(assetUrl, pivoted);

  // 6. Initial placement: room center on the floor.
  const floorY = room ? room.floorY : 0;
  const roomC = room
    ? [
        (room.bounds.min[0] + room.bounds.max[0]) / 2,
        floorY,
        (room.bounds.min[2] + room.bounds.max[2]) / 2,
      ]
    : [0, 0, 0];
  const position: Vec3 = (opts?.position ?? [roomC[0], floorY, roomC[2]]) as Vec3;

  const sceneObject: SceneObject = {
    id: uuid(label.replace(/\s+/g, "-").toLowerCase()),
    label,
    assetUrl,
    transform: { position, rotationY: 0, scale: scaleFactor },
    rawSize,
    targetHeight,
    verified: "pending",
  };

  // 7. Recompute worldBBox from the placed, scaled object.
  sceneObject.worldBBox = computeWorldBBox(sceneObject);

  return { sceneObject, object3d: pivoted };
}
