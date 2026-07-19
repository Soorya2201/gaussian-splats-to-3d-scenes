// Small pure geometry helpers shared by the loader and the resolver.
import * as THREE from "three";
import type { BBox, Vec3, SceneObject } from "../types/scene";

export function box3ToBBox(box: THREE.Box3): BBox {
  const size = new THREE.Vector3();
  box.getSize(size);
  return {
    min: [box.min.x, box.min.y, box.min.z],
    max: [box.max.x, box.max.y, box.max.z],
    size: [size.x, size.y, size.z],
  };
}

export function bboxCenter(b: BBox): Vec3 {
  return [
    (b.min[0] + b.max[0]) / 2,
    (b.min[1] + b.max[1]) / 2,
    (b.min[2] + b.max[2]) / 2,
  ];
}

export function halfSize(b: BBox): Vec3 {
  return [b.size[0] / 2, b.size[1] / 2, b.size[2] / 2];
}

// Compute the world-space AABB for a placed object from its raw size, scale and
// bottom-center pivot at `position`. Because the pivot is bottom-center, the box
// spans [x-hx, x+hx] x [y, y+h] x [z-hz, z+hz]. Yaw rotation is approximated by
// swelling the horizontal footprint to the rotated bounds (adequate for the
// collision guard and surface math; exact yaw AABB is not required).
export function computeWorldBBox(obj: SceneObject): BBox {
  const [sx, sy, sz] = obj.rawSize;
  const s = obj.transform.scale;
  let w = sx * s;
  let d = sz * s;
  const h = sy * s;

  // Rotated horizontal footprint (axis-aligned bound of a rotated rectangle).
  const c = Math.abs(Math.cos(obj.transform.rotationY));
  const sn = Math.abs(Math.sin(obj.transform.rotationY));
  const rw = w * c + d * sn;
  const rd = w * sn + d * c;
  w = rw;
  d = rd;

  const [px, py, pz] = obj.transform.position;
  const min: Vec3 = [px - w / 2, py, pz - d / 2];
  const max: Vec3 = [px + w / 2, py + h, pz + d / 2];
  return { min, max, size: [w, h, d] };
}

// AABB overlap test with a small epsilon so face-touching is not a collision.
export function boxesIntersect(a: BBox, b: BBox, eps = 1e-3): boolean {
  return (
    a.min[0] < b.max[0] - eps &&
    a.max[0] > b.min[0] + eps &&
    a.min[1] < b.max[1] - eps &&
    a.max[1] > b.min[1] + eps &&
    a.min[2] < b.max[2] - eps &&
    a.max[2] > b.min[2] + eps
  );
}
