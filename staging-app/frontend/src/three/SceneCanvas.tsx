// The R3F <Canvas>. MUST set preserveDrawingBuffer:true or toDataURL returns a
// blank image (Spec Section 13). Renders room + objects, registers the
// screenshot capturer, and wires OrbitControls.
import { Suspense, useEffect, useRef } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { OrbitControls, Grid } from "@react-three/drei";
import * as THREE from "three";
import { useSceneStore } from "../store/sceneStore";
import { Room } from "./Room";
import { SceneObject } from "./SceneObject";
import { registerCapturer } from "./capture";
import { registerExportRoot } from "./exportBridge";

interface Props {
  roomUrl: string | null;
  roomKind?: "glb" | "splat";
  selectedId?: string | null;
}

// Inner component with renderer access: forces a render then reads the buffer.
function CaptureBridge() {
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);
  const camera = useThree((s) => s.camera);

  useEffect(() => {
    registerCapturer(() => {
      try {
        gl.render(scene, camera); // ensure a fresh frame is in the buffer
        return gl.domElement.toDataURL("image/jpeg", 0.85);
      } catch {
        return null;
      }
    });
  }, [gl, scene, camera]);

  return null;
}

export function SceneCanvas({ roomUrl, roomKind = "glb", selectedId }: Props) {
  const objects = useSceneStore((s) => s.objects);
  // Holds exactly the exportable content (room + placed objects) — the orbit
  // grid and selection wireframe live outside this group so GLB export never
  // includes editor-only helpers.
  const exportGroupRef = useRef<THREE.Group>(null);

  useEffect(() => {
    registerExportRoot(() => exportGroupRef.current);
  }, []);

  return (
    <Canvas
      gl={{ preserveDrawingBuffer: true, antialias: true }}
      camera={{ position: [3, 2, 4], fov: 50 }}
      shadows
      onCreated={({ gl }) => {
        gl.outputColorSpace = THREE.SRGBColorSpace;
      }}
    >
      <color attach="background" args={["#0b0d12"]} />
      {/* Minimal fill only — not a second light source. Without any ambient term,
          faces turned away from the sun light below render pure black; this just
          keeps shadow-side geometry visibly readable. */}
      <ambientLight intensity={0.12} />
      {/* The single light source illuminating the room — a directional "sun" light
          with real shadow casting. Shadow-map size and frustum are sized generously
          so shadows stay sharp across both the small procedural room and larger
          imported rooms. */}
      <directionalLight
        position={[5, 8, 5]}
        intensity={2.2}
        castShadow
        target-position={[0, 0, 0]}
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-8}
        shadow-camera-right={8}
        shadow-camera-top={8}
        shadow-camera-bottom={-8}
        shadow-camera-near={0.1}
        shadow-camera-far={30}
        shadow-bias={-0.0015}
      />

      <Suspense fallback={null}>
        {!roomUrl && (
          <Grid
            args={[20, 20]}
            cellColor="#2a2f3a"
            sectionColor="#3a4152"
            infiniteGrid
            fadeDistance={30}
          />
        )}
        <group ref={exportGroupRef}>
          {roomUrl && <Room assetUrl={roomUrl} kind={roomKind} />}
          {objects.map((o) => (
            <SceneObject key={o.id} data={o} selected={o.id === selectedId} />
          ))}
        </group>
      </Suspense>

      <OrbitControls makeDefault target={[0, 0.8, 0]} />
      <CaptureBridge />
    </Canvas>
  );
}
