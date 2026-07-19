// The Resolver — relation -> transform. Spec Section 8.
// Pure functions, no model calls. Assumes bottom-center pivots and that every
// object's worldBBox is current. ~150 lines.
import type {
  SceneGraph,
  SceneObject,
  RoomScene,
  RelationType,
  Vec3,
  BBox,
} from "../types/scene";
import { bboxCenter, halfSize, computeWorldBBox, boxesIntersect } from "../three/geometry";

const DEFAULT_GAP = 0.05; // meters

function findByLabel(scene: SceneGraph, label: string): SceneObject | undefined {
  const q = label.toLowerCase().trim();
  // exact, then substring both ways (tolerant of "coffee table" vs "table")
  return (
    scene.objects.find((o) => o.label.toLowerCase() === q) ??
    scene.objects.find(
      (o) => o.label.toLowerCase().includes(q) || q.includes(o.label.toLowerCase()),
    )
  );
}

function roomCenter(room: RoomScene): Vec3 {
  return bboxCenter(room.bounds);
}

export interface ResolveInput {
  object: SceneObject;
  relation: RelationType;
  target?: string; // label of target object, or floor/wall/room
  gap?: number;
}

export interface ResolveResult {
  position: Vec3;
  rotationY: number;
}

// Resolve a single relation into a new transform for `object`. The caller is
// responsible for writing the result back into the store and recomputing bboxes.
export function resolve(scene: SceneGraph, input: ResolveInput): ResolveResult {
  const O = input.object;
  const gap = input.gap ?? DEFAULT_GAP;
  const room = scene.room;
  const floorY = room ? room.floorY : 0;
  const oBox = O.worldBBox ?? computeWorldBBox(O);
  const oHalf = halfSize(oBox);

  let position: Vec3 = [...O.transform.position] as Vec3;
  let rotationY = O.transform.rotationY;

  const T = input.target ? findByLabel(scene, input.target) : undefined;
  const tBox = T?.worldBBox ?? (T ? computeWorldBBox(T) : undefined);
  const tCenter = tBox ? bboxCenter(tBox) : undefined;
  const tHalf = tBox ? halfSize(tBox) : undefined;

  switch (input.relation) {
    case "on_floor":
      position = [position[0], floorY, position[2]];
      break;

    case "center_of_room": {
      const c = room ? roomCenter(room) : [0, 0, 0];
      position = [c[0], floorY, c[2]];
      break;
    }

    case "on_top_of":
      if (tBox && tCenter) {
        // bottom-center pivot: set y directly to the target's top surface
        position = [tCenter[0], tBox.max[1], tCenter[2]];
      }
      break;

    case "against_wall":
      if (room) {
        position = snapToNearestWall(O, room, oHalf, gap);
        rotationY = wallFacingYaw(position, room);
        position = [position[0], floorY, position[2]];
      }
      break;

    case "left_of": // left = negative X by convention
      if (tCenter && tHalf) {
        position = [tCenter[0] - tHalf[0] - gap - oHalf[0], floorY, tCenter[2]];
      }
      break;

    case "right_of": // mirror of left_of
      if (tCenter && tHalf) {
        position = [tCenter[0] + tHalf[0] + gap + oHalf[0], floorY, tCenter[2]];
      }
      break;

    case "in_front_of": // front = +Z by convention
      if (tCenter && tHalf) {
        position = [tCenter[0], floorY, tCenter[2] + tHalf[2] + gap + oHalf[2]];
      }
      break;

    case "behind": // mirror of in_front_of, -Z
      if (tCenter && tHalf) {
        position = [tCenter[0], floorY, tCenter[2] - tHalf[2] - gap - oHalf[2]];
      }
      break;

    case "near": // simplest correct default: +X side with a 0.3m gap
      if (tCenter && tHalf) {
        position = [tCenter[0] + tHalf[0] + oHalf[0] + 0.3, floorY, tCenter[2]];
      }
      break;
  }

  // Collision guard: push O clear of any object it overlaps (except its support
  // target), along the shorter overlap axis, capped so we never fling it away.
  const candidate: SceneObject = {
    ...O,
    transform: { ...O.transform, position, rotationY },
  };
  candidate.worldBBox = computeWorldBBox(candidate);
  const resolved = separateFromOthers(scene, candidate, T?.id);
  position = resolved.transform.position;

  return { position, rotationY };
}

// Snap object's back face to the nearest of the 4 room-bound vertical planes.
function snapToNearestWall(
  O: SceneObject,
  room: RoomScene,
  oHalf: Vec3,
  gap: number,
): Vec3 {
  const p = O.transform.position;
  const b = room.bounds;
  const dists = [
    { axis: "maxX", d: Math.abs(b.max[0] - p[0]) },
    { axis: "minX", d: Math.abs(p[0] - b.min[0]) },
    { axis: "maxZ", d: Math.abs(b.max[2] - p[2]) },
    { axis: "minZ", d: Math.abs(p[2] - b.min[2]) },
  ].sort((a, c) => a.d - c.d);

  const nearest = dists[0].axis;
  const x = p[0];
  const z = p[2];
  switch (nearest) {
    case "maxX":
      return [b.max[0] - oHalf[0] - gap, p[1], z];
    case "minX":
      return [b.min[0] + oHalf[0] + gap, p[1], z];
    case "maxZ":
      return [x, p[1], b.max[2] - oHalf[2] - gap];
    default:
      return [x, p[1], b.min[2] + oHalf[2] + gap];
  }
}

// Yaw so the object's front (+Z local) points into the room from the wall it sits on.
function wallFacingYaw(pos: Vec3, room: RoomScene): number {
  const b = room.bounds;
  const c = bboxCenter(room.bounds);
  const dMaxX = Math.abs(b.max[0] - pos[0]);
  const dMinX = Math.abs(pos[0] - b.min[0]);
  const dMaxZ = Math.abs(b.max[2] - pos[2]);
  const dMinZ = Math.abs(pos[2] - b.min[2]);
  const m = Math.min(dMaxX, dMinX, dMaxZ, dMinZ);
  if (m === dMaxX) return -Math.PI / 2; // face -X (toward center)
  if (m === dMinX) return Math.PI / 2; // face +X
  if (m === dMaxZ) return Math.PI; // face -Z
  void c;
  return 0; // minZ wall -> face +Z
}

// Push `obj` out of any other object's box (skipping the support target) along
// the axis of least penetration, capped at 1m of total displacement.
function separateFromOthers(
  scene: SceneGraph,
  obj: SceneObject,
  supportId?: string,
  cap = 1.0,
): SceneObject {
  let moved = { ...obj, transform: { ...obj.transform } };
  let box = moved.worldBBox ?? computeWorldBBox(moved);
  let totalPush = 0;

  for (const other of scene.objects) {
    if (other.id === obj.id || other.id === supportId) continue;
    const ob = other.worldBBox ?? computeWorldBBox(other);
    if (!boxesIntersect(box, ob)) continue;

    // overlap along X and Z (ignore Y — stacking is intentional)
    const overlapX =
      Math.min(box.max[0], ob.max[0]) - Math.max(box.min[0], ob.min[0]);
    const overlapZ =
      Math.min(box.max[2], ob.max[2]) - Math.max(box.min[2], ob.min[2]);
    if (overlapX <= 0 && overlapZ <= 0) continue;

    const pos = moved.transform.position;
    if (overlapX < overlapZ) {
      const dir = pos[0] >= bboxCenter(ob)[0] ? 1 : -1;
      const push = Math.min(overlapX + 1e-3, cap - totalPush);
      pos[0] += dir * push;
      totalPush += push;
    } else {
      const dir = pos[2] >= bboxCenter(ob)[2] ? 1 : -1;
      const push = Math.min(overlapZ + 1e-3, cap - totalPush);
      pos[2] += dir * push;
      totalPush += push;
    }
    moved.worldBBox = computeWorldBBox(moved);
    box = moved.worldBBox;
    if (totalPush >= cap) break;
  }
  return moved;
}

// Convenience helper for callers that only need the halfSize of a box.
export function halfOf(b: BBox): Vec3 {
  return halfSize(b);
}
