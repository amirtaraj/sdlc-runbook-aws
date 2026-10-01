// Thin typed client for the FastAPI backend. Every call carries the signed-in user's
// Authorization header, supplied by the active auth provider (mock or Entra ID).
import type { DocumentExtract, DocumentSource, Metrics, Runbook, RunSummary, RunView, TechStack } from "../types/run";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly reasons: string[] = [],
  ) {
    super(message);
  }
}

type AuthHeaderProvider = () => Promise<string | null>;
let authHeader: AuthHeaderProvider = async () => null;
let onUnauthorized: () => void = () => {};

export function configureApiAuth(provider: AuthHeaderProvider, unauthorized: () => void) {
  authHeader = provider;
  onUnauthorized = unauthorized;
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  const auth = await authHeader();
  // FormData sets its own multipart Content-Type (with boundary); everything else is JSON.
  const headers: Record<string, string> = {};
  if (!(init?.body instanceof FormData)) headers["Content-Type"] = "application/json";
  if (auth) headers.Authorization = auth;
  let res: Response;
  try {
    res = await fetch(BASE_URL + path, { ...init, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the runbook server. Is the API running on port 8000?");
  }
  if (!res.ok) {
    let message = res.statusText;
    let reasons: string[] = [];
    try {
      const body = await res.json();
      if (body.detail?.code === "guardrail_blocked") {
        reasons = body.detail.reasons;
        message = "Blocked by guardrails";
      } else {
        message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // keep statusText
    }
    if (res.status === 401) onUnauthorized();
    throw new ApiError(res.status, message, reasons);
  }
  return res;
}

const json = async <T>(path: string, init?: RequestInit): Promise<T> => (await request(path, init)).json();

const post = <T>(path: string, body?: unknown) =>
  json<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const runsApi = {
  me: () => json<{ name: string; email: string; roles: string[]; auth_type: string }>("/me"),
  runbook: () => json<Runbook>("/runbook"),
  metrics: () => json<Metrics>("/metrics"),
  list: () => json<RunSummary[]>("/runs"),
  get: (runId: string) => json<RunView>(`/runs/${runId}`),
  techStacks: () => json<{ default: string; stacks: TechStack[] }>("/tech-stacks"),
  start: (requirementText: string, source?: DocumentSource, techStackId?: string) =>
    post<RunView>("/runs", {
      requirement_text: requirementText,
      ...(source ? { source } : {}),
      ...(techStackId ? { tech_stack_id: techStackId } : {}),
    }),
  extractDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return json<DocumentExtract>("/documents/extract", { method: "POST", body: form });
  },
  approve: (runId: string, overrideReason?: string) =>
    post<RunView>(`/runs/${runId}/approve`, overrideReason ? { override_reason: overrideReason } : {}),
  edit: (runId: string, correctionText: string) =>
    post<RunView>(`/runs/${runId}/edit`, { correction_text: correctionText }),
  reject: (runId: string) => post<RunView>(`/runs/${runId}/reject`),
  retry: (runId: string) => post<RunView>(`/runs/${runId}/retry`),
  publish: (runId: string) => post<RunView>(`/runs/${runId}/publish`),
  document: async (runId: string) => (await request(`/runs/${runId}/document`)).text(),
  stageDocument: async (runId: string, stage: string) => (await request(`/runs/${runId}/documents/${stage}`)).text(),
  specPack: async (runId: string) => (await request(`/runs/${runId}/spec-pack`)).blob(),
};

// Public endpoint, no auth: tells the browser which sign-in to use.
export interface AuthConfig {
  mode: "mock" | "entra";
  roles: string[];
  tenant_id?: string;
  client_id?: string;
  api_scope?: string;
}

export async function fetchAuthConfig(): Promise<AuthConfig> {
  const res = await fetch(`${BASE_URL}/auth/config`).catch(() => null);
  if (!res?.ok) throw new ApiError(0, "Cannot reach the runbook server. Is the API running on port 8000?");
  return res.json();
}
