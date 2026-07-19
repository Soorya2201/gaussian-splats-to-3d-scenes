// Command controller: utterance -> command JSON -> resolver -> scene graph ->
// (optional) vision validation. Shared by the text box and the voice hook.
import { parseCommand, type Command } from "./llm/parseCommand";
import { validateAndCorrect } from "./llm/validate";
import { loadObject } from "./three/loadObject";
import { useSceneStore } from "./store/sceneStore";
import { listAssets } from "./llm/scene";
import type { RelationType } from "./types/scene";

export interface RunResult {
  ok: boolean;
  message: string;
  command?: Command;
}

// Whether to run the vision validator after a placement. Toggled from the UI.
let validationEnabled = true;
export function setValidationEnabled(on: boolean) {
  validationEnabled = on;
}
export function isValidationEnabled() {
  return validationEnabled;
}

async function addObjectByLabel(label: string): Promise<RunResult> {
  const store = useSceneStore.getState();
  const assets = await listAssets();
  const match =
    assets.find((a) => a.label.toLowerCase() === label.toLowerCase()) ??
    assets.find(
      (a) =>
        a.label.toLowerCase().includes(label.toLowerCase()) ||
        label.toLowerCase().includes(a.label.toLowerCase()),
    );
  if (!match) {
    return { ok: false, message: `No asset found for "${label}".` };
  }
  const { sceneObject } = await loadObject(match.url, label, store.room);
  store.addObject(sceneObject);
  // A bare "add" has no explicit relation yet, but it still lands on the
  // floor at room center by construction — validate that contact + scale
  // are plausible immediately, instead of leaving it "pending" forever
  // until the user happens to issue a separate placement command.
  if (validationEnabled) {
    void validateAndCorrect(sceneObject.id, "on_floor", "the floor");
  }
  return { ok: true, message: `Added ${label}.` };
}

export async function runCommand(text: string): Promise<RunResult> {
  const store = useSceneStore.getState();
  const objectList = store.objects.map((o) => ({ id: o.id, label: o.label }));

  let command: Command;
  try {
    command = await parseCommand({
      text,
      objects: objectList,
      hasRoom: !!store.room,
    });
  } catch (e) {
    return { ok: false, message: `Parse failed: ${String(e)}` };
  }

  switch (command.action) {
    case "add": {
      const r = await addObjectByLabel(command.object);
      return { ...r, command };
    }
    case "remove": {
      const removed = store.removeByLabel(command.object);
      return {
        ok: removed,
        message: removed ? `Removed ${command.object}.` : `No "${command.object}" to remove.`,
        command,
      };
    }
    case "clear":
      store.clearObjects();
      return { ok: true, message: "Cleared all objects.", command };
    case "scale":
      store.scaleObject(command.object, command.factor);
      return { ok: true, message: `Scaled ${command.object} by ${command.factor}.`, command };
    case "error":
      return { ok: false, message: command.message, command };
    case "place": {
      const placed = store.placeRelation(
        command.object,
        command.relation as RelationType,
        command.target ?? undefined,
        command.align ?? undefined,
      );
      if (!placed) {
        return { ok: false, message: `No object called "${command.object}".`, command };
      }
      if (command.targetHeight && command.targetHeight > 0) {
        const factor = command.targetHeight / placed.targetHeight;
        store.scaleObject(placed.label, factor);
      }
      // fire-and-forget validation (updates badges asynchronously)
      if (validationEnabled) {
        void validateAndCorrect(
          placed.id,
          command.relation as RelationType,
          command.target ?? "the room",
        );
      }
      return {
        ok: true,
        message: `Placed ${command.object} ${command.relation.replace(/_/g, " ")} ${
          command.target ?? "room"
        }.`,
        command,
      };
    }
  }
}
