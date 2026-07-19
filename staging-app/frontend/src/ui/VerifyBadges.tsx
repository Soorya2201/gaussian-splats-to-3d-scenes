// Pass / flagged / pending indicator for an object.
import type { VerifyState } from "../types/scene";

export function VerifyBadge({ state, note }: { state: VerifyState; note?: string }) {
  const label = state === "pass" ? "verified" : state === "flagged" ? "flagged" : "pending";
  return (
    <span className={`badge ${state}`} title={note ?? ""}>
      <span className="dot" />
      {label}
    </span>
  );
}
