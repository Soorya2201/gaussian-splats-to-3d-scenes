// Scale table — sane real-world heights in meters. Spec Section 9.
// The LLM may override via targetHeight, but this is the fallback so nothing
// is ever wildly mis-sized.

export interface ScaleEntry {
  height: number;
  axis?: "y" | "footprint";
}

export const SCALE_TABLE: Record<string, ScaleEntry> = {
  table: { height: 0.75 },
  desk: { height: 0.75 },
  chair: { height: 0.9 },
  sofa: { height: 0.85 },
  lamp: { height: 0.5 },
  floorlamp: { height: 1.6 },
  plant: { height: 0.6 },
  rug: { height: 0.02, axis: "footprint" },
  bookshelf: { height: 1.8 },
  bed: { height: 0.6 },
  tv: { height: 0.65 },
  vase: { height: 0.3 },
  apple: { height: 0.08 },
  default: { height: 0.5 },
};

// Match the object label to the closest key (lowercase, substring match, else default).
export function lookupScale(label: string): ScaleEntry {
  const key = label.toLowerCase().trim();
  if (SCALE_TABLE[key]) return SCALE_TABLE[key];
  // substring match in either direction (e.g. "coffee table" -> "table",
  // "floor lamp" -> "floorlamp" won't match with a space, so also strip spaces)
  const compact = key.replace(/\s+/g, "");
  for (const k of Object.keys(SCALE_TABLE)) {
    if (k === "default") continue;
    if (key.includes(k) || compact.includes(k) || k.includes(compact)) {
      return SCALE_TABLE[k];
    }
  }
  return SCALE_TABLE.default;
}
