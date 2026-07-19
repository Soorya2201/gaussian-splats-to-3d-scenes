// Text box + voice button + status. Also exposes quick manual relation chips
// (the M3 buttons) that call the resolver directly, for demo fallback.
import { useState } from "react";
import { runCommand, setValidationEnabled, isValidationEnabled } from "../controller";
import { useSpeech } from "../voice/useSpeech";
import { useSceneStore } from "../store/sceneStore";
import type { RelationType } from "../types/scene";

const QUICK: { label: string; run: () => void }[] = [];

export function CommandBar() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ msg: string; kind: "ok" | "err" | "" }>({
    msg: "",
    kind: "",
  });
  const [validate, setValidate] = useState(isValidationEnabled());
  const objects = useSceneStore((s) => s.objects);
  const placeRelation = useSceneStore((s) => s.placeRelation);

  async function submit(utterance: string) {
    const t = utterance.trim();
    if (!t || busy) return;
    setBusy(true);
    setStatus({ msg: "Thinking…", kind: "" });
    try {
      const r = await runCommand(t);
      setStatus({ msg: r.message, kind: r.ok ? "ok" : "err" });
      if (r.ok) setText("");
    } catch (e) {
      setStatus({ msg: String(e), kind: "err" });
    } finally {
      setBusy(false);
    }
  }

  const { listening, supported, start, stop } = useSpeech((spoken) => {
    setText(spoken);
    void submit(spoken);
  });

  // Manual relation quick-actions (M3): use first two objects if present.
  function quickPlace(rel: RelationType) {
    if (objects.length === 0) return;
    const o = objects[objects.length - 1];
    const t = objects.length > 1 ? objects[0] : undefined;
    placeRelation(o.label, rel, t?.label);
    setStatus({
      msg: `Manually placed ${o.label} ${rel.replace(/_/g, " ")} ${t?.label ?? "room"}.`,
      kind: "ok",
    });
  }

  return (
    <div className="commandbar">
      <div className="row">
        <input
          className="input"
          placeholder='e.g. "put the lamp on the coffee table"'
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void submit(text);
          }}
          disabled={busy}
        />
        <button
          className={listening ? "primary" : ""}
          onClick={() => (listening ? stop() : start())}
          disabled={!supported || busy}
          title={supported ? "Voice (Chromium only)" : "Voice not supported in this browser"}
        >
          {listening ? "● Listening" : "🎤 Voice"}
        </button>
        <button className="primary" onClick={() => void submit(text)} disabled={busy}>
          Send
        </button>
      </div>

      <div className="row wrap" style={{ marginTop: 8 }}>
        <span style={{ fontSize: 11, color: "var(--muted)" }}>Quick:</span>
        <button className="chip" onClick={() => quickPlace("on_top_of")}>
          on top of
        </button>
        <button className="chip" onClick={() => quickPlace("against_wall")}>
          against wall
        </button>
        <button className="chip" onClick={() => quickPlace("left_of")}>
          left of
        </button>
        <button className="chip" onClick={() => quickPlace("center_of_room")}>
          center
        </button>
        <label className="toggle" style={{ marginLeft: "auto" }}>
          <input
            type="checkbox"
            checked={validate}
            onChange={(e) => {
              setValidate(e.target.checked);
              setValidationEnabled(e.target.checked);
            }}
          />
          vision validation
        </label>
      </div>

      <div className={`status ${status.kind}`}>{status.msg}</div>
    </div>
  );
}

void QUICK;
