// Mirrors the backend API. Stage outputs are generic: their shape comes from each stage's
// JSON schema in RUNBOOK.md (served by GET /runbook), so the UI renders any stage.

export type StageId = string;

export type RunStatus = "not_started" | "pending_approval" | "failed" | "completed" | "rejected";

export type Decision = "approved" | "edited" | "rejected";

export type StageOutput = Record<string, unknown>;

export interface JsonSchema {
  type: "object" | "array" | "string" | "boolean";
  properties?: Record<string, JsonSchema>;
  items?: JsonSchema;
  enum?: string[];
}

export interface GateSpec {
  check: string;
  args: string;
  description: string;
}

export interface StageSpec {
  id: StageId;
  title: string;
  purpose: string;
  edit_mode: "revise" | "clarify";
  schema: JsonSchema;
  gates: GateSpec[];
  /** Per-item stage (one output per task), collected under `collect_as`. */
  for_each: boolean;
  collect_as: string | null;
}

export interface TechStack {
  id: string;
  name: string;
  layers: Record<string, string>;
  conventions: string[];
}

export interface Runbook {
  stages: StageSpec[];
}

export interface GateResult extends GateSpec {
  passed: boolean;
  detail: string;
}

export interface Reference {
  id: string;
  title: string;
}

export interface StageRecord {
  stage: StageId;
  output: StageOutput;
  decision: Decision;
  edit_note: string | null;
  actor: string;
  gates: GateResult[];
  gate_override: string | null;
  references: Reference[];
  pii_flags: string[];
}

export interface PublishedItem {
  task_id: string;
  work_item_id: number;
  title: string;
  url: string;
}

export interface Usage {
  llm_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

export interface RunSummary {
  run_id: string;
  title: string;
  status: RunStatus;
  updated_at: string;
}

/** The uploaded document a requirement came from. */
export interface DocumentSource {
  filename: string;
  kind: string;
  sha256: string;
  pages: number | null;
  chars: number;
  redacted: boolean;
}

/** Result of POST /documents/extract: the text plus the guardrail review. */
export interface DocumentExtract extends Omit<DocumentSource, "redacted"> {
  size_bytes: number;
  text: string;
  blocked_reasons: string[];
  pii_categories: string[];
  redacted_text: string | null;
}

export interface RunView extends RunSummary {
  requirement_text: string;
  source: DocumentSource | null;
  tech_stack: { id: string; name: string } | null;
  spec_pack_available: boolean;
  created_by: string;
  stages: StageId[];
  stage: StageId | null;
  deployment: string | null;
  output: StageOutput | null;
  refusal: string | null;
  gates: GateResult[];
  references: Reference[];
  pii_flags: string[];
  edit_notes: string[];
  clarifications: string[];
  history: StageRecord[];
  published: PublishedItem[];
  error: string | null;
  agent_seconds: number;
  usage: Usage;
  created_at: string;
  document_markdown: string | null;
}

interface LatencyStats {
  calls: number;
  success_rate: number | null;
  avg_latency_ms: number;
  p95_latency_ms: number;
}

export interface Metrics {
  runs: { total: number; by_status: Record<RunStatus, number>; completion_rate: number | null };
  llm: LatencyStats & {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
    by_stage: Record<string, LatencyStats & { total_tokens: number }>;
    recent_errors: { stage: string; error: string; timestamp: string }[];
  };
  services: Record<string, LatencyStats>;
}
