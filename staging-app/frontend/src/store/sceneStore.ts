// Zustand store holding the Scene Graph (the single source of truth).
// Every mutation bumps `version` and recomputes worldBBox where relevant.
import { create } from "zustand";
import type {
  SceneGraph,
  SceneObject,
  RoomScene,
  RelationType,
  Vec3,
} from "../types/scene";
import { computeWorldBBox } from "../three/geometry";
import { resolve } from "../resolver/resolver";

export interface SceneState extends SceneGraph {
  // room
  setRoom: (room: RoomScene) => void;
  // objects
  addObject: (obj: SceneObject) => void;
  removeObject: (id: string) => void;
  removeByLabel: (label: string) => boolean;
  clearObjects: () => void;
  updateTransform: (id: string, patch: Partial<SceneObject["transform"]>) => void;
  setVerified: (id: string, verified: SceneObject["verified"], note?: string) => void;
  // high-level ops
  placeRelation: (
    objectLabel: string,
    relation: RelationType,
    target?: string,
    align?: "center" | "left" | "right",
  ) => SceneObject | null;
  scaleObject: (label: string, factor: number) => void;
  findByLabel: (label: string) => SceneObject | undefined;
  loadGraph: (graph: SceneGraph) => void;
  snapshot: () => SceneGraph;
}

function recompute(o: SceneObject): SceneObject {
  return { ...o, worldBBox: computeWorldBBox(o) };
}

function labelMatch(o: SceneObject, label: string): boolean {
  const a = o.label.toLowerCase();
  const b = label.toLowerCase().trim();
  return a === b || a.includes(b) || b.includes(a);
}

export const useSceneStore = create<SceneState>((set, get) => ({
  room: null,
  objects: [],
  version: 0,

  setRoom: (room) => set((s) => ({ room, version: s.version + 1 })),

  addObject: (obj) =>
    set((s) => ({ objects: [...s.objects, recompute(obj)], version: s.version + 1 })),

  removeObject: (id) =>
    set((s) => ({
      objects: s.objects.filter((o) => o.id !== id),
      version: s.version + 1,
    })),

  removeByLabel: (label) => {
    const target = get().objects.find((o) => labelMatch(o, label));
    if (!target) return false;
    set((s) => ({
      objects: s.objects.filter((o) => o.id !== target.id),
      version: s.version + 1,
    }));
    return true;
  },

  clearObjects: () => set((s) => ({ objects: [], version: s.version + 1 })),

  updateTransform: (id, patch) =>
    set((s) => ({
      objects: s.objects.map((o) =>
        o.id === id
          ? recompute({ ...o, transform: { ...o.transform, ...patch } })
          : o,
      ),
      version: s.version + 1,
    })),

  setVerified: (id, verified, note) =>
    set((s) => ({
      objects: s.objects.map((o) =>
        o.id === id ? { ...o, verified, validationNote: note } : o,
      ),
      version: s.version + 1,
    })),

  placeRelation: (objectLabel, relation, target, align) => {
    const scene = get();
    const obj = scene.objects.find((o) => labelMatch(o, objectLabel));
    if (!obj) return null;
    const { position, rotationY } = resolve(scene, {
      object: obj,
      relation,
      target,
    });
    const updated = recompute({
      ...obj,
      transform: { ...obj.transform, position: position as Vec3, rotationY },
      relation: { type: relation, target: target ?? "room", align: align ?? "center" },
      verified: "pending",
      validationNote: undefined,
    });
    set((s) => ({
      objects: s.objects.map((o) => (o.id === obj.id ? updated : o)),
      version: s.version + 1,
    }));
    return updated;
  },

  scaleObject: (label, factor) => {
    const obj = get().objects.find((o) => labelMatch(o, label));
    if (!obj) return;
    get().updateTransform(obj.id, { scale: obj.transform.scale * factor });
    get().setVerified(obj.id, "pending");
  },

  findByLabel: (label) => get().objects.find((o) => labelMatch(o, label)),

  loadGraph: (graph) =>
    set(() => ({
      room: graph.room,
      objects: graph.objects.map(recompute),
      version: (graph.version ?? 0) + 1,
    })),

  snapshot: () => {
    const { room, objects, version } = get();
    return { room, objects, version };
  },
}));
