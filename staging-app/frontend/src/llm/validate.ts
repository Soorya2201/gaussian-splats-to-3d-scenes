// Captures a screenshot and calls backend /validate-placement, then runs the
// capped (3) retry loop applying small nudges from the model's suggestion.
// Spec Section 11.
import { postJSON } from "./api";
import { captureScreenshot } from "../three/capture";
import { useSceneStore } from "../store/sceneStore";
import type { SceneObject, RelationType } from "../types/scene";

export type Suggestion =
  | "move_up"
  | "move_down"
  | "move_left"
  | "move_right"
  | "scale_up"
  | "scale_down"
  | "none";

export interface ValidateResponse {
  pass: boolean;
  reason: string;
  suggestion: Suggestion;
}

const RELATION_PHRASE: Record<RelationType, string> = {
  on_floor: "on the floor",
  on_top_of: "on top of",
  against_wall: "against the wall",
  left_of: "to the left of",
  right_of: "to the right of",
  in_front_of: "in front of",
  behind: "behind",
  near: "near",
  center_of_room: "in the center of the room",
};

function nextFrame(): Promise<void> {
  return new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
}

async function validateOnce(
  obj: SceneObject,
  relation: RelationType,
  target: string,
): Promise<ValidateResponse | null> {
  await nextFrame(); // let the latest transform render before capturing
  const image = captureScreenshot();
  if (!image) return null;
  return postJSON<ValidateResponse>("/validate-placement", {
    image_base64: image,
    object: obj.label,
    relation_phrase: RELATION_PHRASE[relation],
    target,
  });
}

// Apply a small nudge for a suggestion, mutating the store. Returns true if it
// changed anything (i.e. we should re-validate).
function applyNudge(obj: SceneObject, s: Suggestion): boolean {
  const store = useSceneStore.getState();
  const [x, y, z] = obj.transform.position;
  switch (s) {
    case "move_down":
      store.updateTransform(obj.id, { position: [x, y - 0.03, z] });
      return true;
    case "move_up":
      store.updateTransform(obj.id, { position: [x, y + 0.03, z] });
      return true;
    case "move_left":
      store.updateTransform(obj.id, { position: [x - 0.05, y, z] });
      return true;
    case "move_right":
      store.updateTransform(obj.id, { position: [x + 0.05, y, z] });
      return true;
    case "scale_down":
      store.updateTransform(obj.id, { scale: obj.transform.scale * 0.9 });
      return true;
    case "scale_up":
      store.updateTransform(obj.id, { scale: obj.transform.scale * 1.1 });
      return true;
    case "none":
      return false;
  }
}

// Validate and (up to 3 tries) auto-correct. Never loops unbounded.
export async function validateAndCorrect(
  objectId: string,
  relation: RelationType,
  target: string,
  maxRetries = 3,
): Promise<void> {
  const store = useSceneStore.getState();
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const obj = useSceneStore.getState().objects.find((o) => o.id === objectId);
    if (!obj) return;

    let result: ValidateResponse | null;
    try {
      result = await validateOnce(obj, relation, target);
    } catch (e) {
      store.setVerified(objectId, "flagged", `Validator error: ${String(e)}`);
      return;
    }
    if (!result) {
      store.setVerified(objectId, "flagged", "Could not capture a screenshot.");
      return;
    }

    if (result.pass) {
      store.setVerified(objectId, "pass", result.reason);
      return;
    }

    // failed — nudge if retries remain, else flag
    if (attempt < maxRetries && result.suggestion !== "none") {
      applyNudge(obj, result.suggestion);
      continue;
    }
    store.setVerified(objectId, "flagged", result.reason);
    return;
  }
}
