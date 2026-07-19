// Renders the room (GLB or Gaussian splat) and normalizes it so the floor
// sits at world y = 0. Writes the resulting RoomScene into the store.
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { useGLTF } from "@react-three/drei";
import { useSceneStore } from "../store/sceneStore";
import { box3ToBBox } from "./geometry";
import type { RoomScene } from "../types/scene";

interface RoomProps {
  assetUrl: string;
  kind?: "glb" | "splat";
}

// Imported room GLBs are not guaranteed to be authored at true 1-unit-1-meter
// (very common with downloaded/scanned assets — e.g. modeled in centimeters
// with no unit conversion applied on export). Object scale is already
// normalized against real-world heights via the scale table; the room itself
// was NOT, which let a correctly-sized 0.5m lamp tower over a room whose raw
// mesh measured under 1m tall. Mirror the same heuristic for the room: if its
// raw height falls outside a plausible ceiling-height range, correct it
// toward a sane target rather than trusting the raw mesh scale blindly.
const MIN_PLAUSIBLE_ROOM_HEIGHT = 1.5; // meters
const MAX_PLAUSIBLE_ROOM_HEIGHT = 8.0; // meters
const TARGET_ROOM_HEIGHT = 2.6; // typical ceiling height; matches the procedural demo room

export function Room({ assetUrl, kind = "glb" }: RoomProps) {
  const setRoom = useSceneStore((s) => s.setRoom);
  const groupRef = useRef<THREE.Group>(null);
  const [normalized, setNormalized] = useState(false);

  // GLB path (the reliable default). Splat path is a fallback the spec allows.
  const { scene } = useGLTF(assetUrl);
  const cloned = useMemo(() => {
    const c = scene.clone(true);
    // Meshes default to castShadow/receiveShadow = false — without this the
    // room stays unlit-looking regardless of the light rig, since nothing in
    // the scene actually participates in shadow mapping.
    c.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        child.castShadow = true;
        child.receiveShadow = true;
      }
    });
    return c;
  }, [scene]);

  useEffect(() => {
    if (!cloned) return;

    // Auto-correct implausible room scale (see comment above) before doing
    // anything else, so floor-normalization and bounds below reflect the
    // corrected size.
    const rawBox = new THREE.Box3().setFromObject(cloned);
    const rawHeight = rawBox.max.y - rawBox.min.y;
    if (
      rawHeight > 0 &&
      (rawHeight < MIN_PLAUSIBLE_ROOM_HEIGHT || rawHeight > MAX_PLAUSIBLE_ROOM_HEIGHT)
    ) {
      cloned.scale.setScalar(TARGET_ROOM_HEIGHT / rawHeight);
      cloned.updateMatrixWorld(true);
    }

    // Measure the room AABB, then translate so its lowest point is at y = 0.
    const box = new THREE.Box3().setFromObject(cloned);
    const shiftY = -box.min.y;
    cloned.position.y = shiftY;
    cloned.updateMatrixWorld(true);

    // Re-measure after the shift to store normalized bounds (floor at 0).
    const normBox = new THREE.Box3().setFromObject(cloned);
    const room: RoomScene = {
      id: "room-0",
      assetUrl,
      kind,
      floorY: 0,
      bounds: box3ToBBox(normBox),
    };
    setRoom(room);
    setNormalized(true);
  }, [cloned, assetUrl, kind, setRoom]);

  return (
    <group ref={groupRef}>
      <primitive object={cloned} visible={normalized} />
    </group>
  );
}

// Preload helper so the room mesh is ready before objects reference its bounds.
export function preloadRoom(url: string) {
  useGLTF.preload(url);
}
