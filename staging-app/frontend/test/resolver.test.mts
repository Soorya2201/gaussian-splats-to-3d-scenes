// Focused verification of the deterministic resolver + geometry math.
// Run: npx tsx test/resolver.test.mts
import assert from "node:assert";
import { resolve } from "../src/resolver/resolver.ts";
import { computeWorldBBox } from "../src/three/geometry.ts";
import type { SceneGraph, SceneObject, RoomScene } from "../src/types/scene.ts";

let pass = 0;
function check(name: string, cond: boolean, extra = "") {
  assert.ok(cond, `FAIL: ${name} ${extra}`);
  pass++;
  console.log(`  ok  ${name}`);
}

function mkObject(label: string, rawSize: [number, number, number], pos: [number, number, number]): SceneObject {
  const o: SceneObject = {
    id: label,
    label,
    assetUrl: `/assets/${label}.glb`,
    transform: { position: pos, rotationY: 0, scale: 1 },
    rawSize,
    targetHeight: rawSize[1],
    verified: "pending",
  };
  o.worldBBox = computeWorldBBox(o);
  return o;
}

const room: RoomScene = {
  id: "room-0",
  assetUrl: "/assets/room.glb",
  kind: "glb",
  floorY: 0,
  bounds: { min: [-2, 0, -2], max: [2, 2.6, 2], size: [4, 2.6, 4] },
};

// --- on_top_of: lamp on table => lamp.y === table top ---
{
  const table = mkObject("table", [0.9, 0.4, 0.5], [0, 0, 0]);
  const lamp = mkObject("lamp", [0.2, 0.5, 0.2], [1, 0, 1]);
  const scene: SceneGraph = { room, objects: [table, lamp], version: 1 };
  const r = resolve(scene, { object: lamp, relation: "on_top_of", target: "table" });
  check("on_top_of sets y to target top (0.4)", Math.abs(r.position[1] - 0.4) < 1e-6, `got ${r.position[1]}`);
  check("on_top_of centers x over target", Math.abs(r.position[0] - 0) < 1e-6, `got ${r.position[0]}`);
}

// --- on_floor: drops to floorY, keeps x/z ---
{
  const chair = mkObject("chair", [0.45, 0.9, 0.45], [1.3, 2, -0.5]);
  const scene: SceneGraph = { room, objects: [chair], version: 1 };
  const r = resolve(scene, { object: chair, relation: "on_floor" });
  check("on_floor drops to y=0", Math.abs(r.position[1]) < 1e-6, `got ${r.position[1]}`);
  check("on_floor keeps x", Math.abs(r.position[0] - 1.3) < 1e-6);
}

// --- center_of_room ---
{
  const sofa = mkObject("sofa", [1.6, 0.85, 0.8], [1, 0, 1]);
  const scene: SceneGraph = { room, objects: [sofa], version: 1 };
  const r = resolve(scene, { object: sofa, relation: "center_of_room" });
  check("center_of_room x==0", Math.abs(r.position[0]) < 1e-6);
  check("center_of_room z==0", Math.abs(r.position[2]) < 1e-6);
}

// --- against_wall: snaps back face to a wall, within bounds ---
{
  const sofa = mkObject("sofa", [1.6, 0.85, 0.8], [1.9, 0, 0]); // near +X wall
  const scene: SceneGraph = { room, objects: [sofa], version: 1 };
  const r = resolve(scene, { object: sofa, relation: "against_wall" });
  const half = (1.6) / 2; // approximate (yaw may rotate footprint)
  check("against_wall stays inside +X bound", r.position[0] <= room.bounds.max[0] + 1e-6, `got ${r.position[0]}`);
  check("against_wall pushed toward wall (x>0.5)", r.position[0] > 0.5, `got ${r.position[0]}`);
  void half;
}

// --- left_of: negative X side of target, no overlap ---
{
  const table = mkObject("table", [0.9, 0.4, 0.5], [0, 0, 0]);
  const lamp = mkObject("lamp", [0.2, 0.5, 0.2], [0, 0, 0]);
  const scene: SceneGraph = { room, objects: [table, lamp], version: 1 };
  const r = resolve(scene, { object: lamp, relation: "left_of", target: "table" });
  check("left_of is negative X of target", r.position[0] < -0.45, `got ${r.position[0]}`);
  // check no interpenetration on X
  const gap = -0.45 - (r.position[0] + 0.1);
  check("left_of clears the table (no overlap)", r.position[0] + 0.1 <= -0.45 + 1e-6, `edge ${r.position[0] + 0.1}`);
  void gap;
}

// --- collision guard: two same-spot objects get separated ---
{
  const a = mkObject("boxA", [0.5, 0.5, 0.5], [0, 0, 0]);
  const b = mkObject("boxB", [0.5, 0.5, 0.5], [0, 0, 0]);
  const scene: SceneGraph = { room, objects: [a, b], version: 1 };
  const r = resolve(scene, { object: b, relation: "on_floor" });
  const moved = Math.abs(r.position[0]) > 0 || Math.abs(r.position[2]) > 0;
  check("collision guard separates overlapping objects", moved, `pos ${r.position}`);
}

console.log(`\nAll ${pass} resolver checks passed.`);
