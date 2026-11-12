import type { Lesion } from "../types";

// One colour per kind of lesion; the legend in ReviewView uses the same table.
export const LEGEND = [
  { key: "small", label: "Small (< 5 mm)", color: "#22d3ee" },
  { key: "medium", label: "Medium (5–15 mm)", color: "#facc15" },
  { key: "large", label: "Large (> 15 mm)", color: "#fb923c" },
  { key: "unsized", label: "Size unknown (no marker)", color: "#38bdf8" },
  { key: "confluent", label: "Confluent / merged", color: "#e879f9" },
  { key: "user", label: "Added by you", color: "#4ade80" },
] as const;

const byKey = Object.fromEntries(LEGEND.map((l) => [l.key, l.color]));

export function lesionColor(l: Lesion): string {
  if (l.source !== "ai") return byKey.user;
  if (l.is_confluent) return byKey.confluent;
  return byKey[l.size_class ?? "unsized"];
}

export function confidenceLabel(c: number): { text: string; tone: "ok" | "warn" | "bad" } {
  if (c >= 0.7) return { text: "High", tone: "ok" };
  if (c >= 0.45) return { text: "Moderate", tone: "warn" };
  return { text: "Low", tone: "bad" };
}
