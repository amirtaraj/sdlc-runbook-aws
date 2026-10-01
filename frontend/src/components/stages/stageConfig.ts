// Display helpers for stages. Labels come from RUNBOOK.md (via GET /runbook); each stage
// position gets its own accent colour (styles/tokens.css --accent-1..8) as a scanning aid.
import type { StageOutput, StageSpec } from "../../types/run";
import { plural } from "../../utils/format";

const ACCENT_COUNT = 8;

export function stageLabel(specs: StageSpec[], stageId: string): string {
  return specs.find((s) => s.id === stageId)?.title ?? stageId.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function accentClass(specs: StageSpec[], stageId: string): string {
  const index = Math.max(0, specs.findIndex((s) => s.id === stageId));
  return `accent-${(index % ACCENT_COUNT) + 1}`;
}

/** One-line description of a collapsed stage: the sizes of its lists, e.g. "5 functional requirements · 3 risks". */
export function summarize(output: StageOutput): string {
  const parts = Object.entries(output)
    .filter(([key, value]) => key !== "refusal" && Array.isArray(value))
    .map(([key, value]) => plural((value as unknown[]).length, key.replace(/_/g, " ").replace(/s$/, "")));
  const first = Object.entries(output).find(([k, v]) => k !== "refusal" && typeof v === "string" && v)?.[1] as string | undefined;
  return parts.length ? parts.slice(0, 3).join(" · ") : (first ?? "");
}
