// Renders one placed object from the scene graph. Reads transform (bottom-center
// pivot, uniform scale, yaw) directly; the geometry was already re-pivoted by
// loadObject, so position maps straight onto the object's origin.
import { useMemo } from "react";
import * as THREE from "three";
import { useGLTF } from "@react-three/drei";
import type { SceneObject as SceneObjectData } from "../types/scene";

interface Props {
  data: SceneObjectData;
  selected?: boolean;
}

export function SceneObject({ data, selected }: Props) {
  const { scene } = useGLTF(data.assetUrl);

  // Clone and re-pivot to bottom-center to match loadObject's measurement.
  const object = useMemo(() => {
    const cloned = scene.clone(true);
    const box = new THREE.Box3().setFromObject(cloned);
    const center = new THREE.Vector3();
    box.getCenter(center);
    cloned.position.set(-center.x, -box.min.y, -center.z);
    // Meshes default to castShadow/receiveShadow = false — enable both so
    // placed objects cast a real shadow onto the floor/room and pick up
    // shadows from each other under the single directional light.
    cloned.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        child.castShadow = true;
        child.receiveShadow = true;
      }
    });
    return cloned;
  }, [scene]);

  const [px, py, pz] = data.transform.position;

  return (
    <group
      position={[px, py, pz]}
      rotation={[0, data.transform.rotationY, 0]}
      scale={data.transform.scale}
    >
      <primitive object={object} />
      {selected && <BBoxHelper data={data} />}
    </group>
  );
}

// Optional selection outline drawn from rawSize (in the group's local, pre-scale
// space, so it tracks the object under the group scale).
function BBoxHelper({ data }: { data: SceneObjectData }) {
  const [w, h, d] = data.rawSize;
  return (
    <mesh position={[0, h / 2, 0]}>
      <boxGeometry args={[w, h, d]} />
      <meshBasicMaterial color="#5b8cff" wireframe transparent opacity={0.35} />
    </mesh>
  );
}
