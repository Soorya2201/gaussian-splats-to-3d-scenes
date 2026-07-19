// Calls backend /parse-command: user utterance + object labels -> one command.
import { postJSON } from "./api";
import type { RelationType } from "../types/scene";

export interface ParseRequest {
  text: string;
  objects: { id: string; label: string }[];
  hasRoom: boolean;
}

export type Command =
  | {
      action: "place";
      object: string;
      relation: RelationType;
      target: string | null;
      align?: "center" | "left" | "right" | null;
      targetHeight?: number | null;
    }
  | { action: "add"; object: string }
  | { action: "remove"; object: string }
  | { action: "scale"; object: string; factor: number }
  | { action: "clear" }
  | { action: "error"; message: string };

export function parseCommand(req: ParseRequest): Promise<Command> {
  return postJSON<Command>("/parse-command", req);
}
