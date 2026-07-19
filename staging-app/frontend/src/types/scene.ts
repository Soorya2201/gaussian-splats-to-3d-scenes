// Core data model — the Scene Graph (single source of truth). Spec Section 5.
// The backend mirrors these as pydantic models (backend/schemas.py).

export type Vec3 = [number, number, number];

export type RelationType =
  | "on_floor"
  | "on_top_of"
  | "against_wall"
  | "left_of"
  | "right_of"
  | "in_front_of"
  | "behind"
  | "near"
  | "center_of_room";

export interface BBox {
  min: Vec3; // world-space axis-aligned box, AFTER transform
  max: Vec3;
  size: Vec3; // max - min
}

export interface ObjectTransform {
  position: Vec3; // world meters, Y-up. This is the BOTTOM-CENTER pivot point.
  rotationY: number; // yaw in radians (we only expose yaw for simplicity)
  scale: number; // uniform scale multiplier applied AFTER normalization
}

export interface ObjectRelation {
  type: RelationType;
  target: string; // another object's label, or "floor" / "wall" / "room"
  align?: "center" | "left" | "right";
  offset?: number; // extra meters of gap, default from resolver
}

export type VerifyState = "pending" | "pass" | "flagged";

export interface SceneObject {
  id: string; // stable uuid, generated on add
  label: string; // "lamp", "sofa" — used by the LLM to refer to it
  assetUrl: string; // /assets/xxx.glb
  transform: ObjectTransform;
  rawSize: Vec3; // bounding-box size of the loaded GLB at scale=1 (for scale calc)
  targetHeight: number; // desired real-world height in meters (from scaleTable or LLM)
  relation?: ObjectRelation;
  worldBBox?: BBox; // recomputed after every transform; used by resolver
  verified: VerifyState;
  validationNote?: string;
}

export interface RoomScene {
  id: string;
  assetUrl: string;
  kind: "glb" | "splat";
  floorY: number; // world Y of floor, normalized to 0 on import
  bounds: BBox; // room extent in world meters
}

export interface SceneGraph {
  room: RoomScene | null;
  objects: SceneObject[];
  version: number; // increment on every mutation (for React re-render + undo later)
}
