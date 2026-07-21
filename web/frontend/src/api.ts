// Typed fetch helpers against web/backend/app.py. Field names/shapes mirror
// web/backend/schemas.py exactly -- FastAPI serializes those pydantic models
// with the same field names, so these interfaces are a hand-kept mirror, not
// a generated one. Keep them in sync if schemas.py changes.

export type NodeKind = "agent" | "gate" | "plumbing";
export type NodeStatus = "pending" | "completed" | "failed" | "paused";

export interface TopologyNode {
  id: string;
  label: string;
  phase: string;
  kind: NodeKind;
}

export interface TopologyEdge {
  source: string;
  target: string;
  label: string | null;
}

export interface FlowNodeStatus {
  id: string;
  status: NodeStatus;
}

export interface FlowStatus {
  paper_id: string;
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  node_status: FlowNodeStatus[];
  paused_gate: string | null;
  gate_payload: Record<string, unknown> | null;
}

export interface PaperSummary {
  paper_id: string;
  title: string;
  keywords: string[];
  abstract: string | null;
  venue: string | null;
  phase: string;
  status: string;
}

export interface PaperDetail extends PaperSummary {
  revision_loop_count: number;
  errors: string[];
  artifacts: Record<string, string>;
  paused: boolean;
  gate_payload: Record<string, unknown> | null;
  running: boolean;
  import_error: string | null;
}

export interface ProvenanceEntry {
  ts: string;
  paper_id: string;
  agent: string;
  model: string | null;
  skill_name: string | null;
  skill_upstream_commit: string | null;
  input_hash: string;
  output_summary: string;
  tokens: Record<string, number>;
  cost_usd: number | null;
  artifacts_written: string[];
  duration_ms: number;
  error: string | null;
}

export interface UsageRow {
  key: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  cost_unknown_calls: number;
}

export interface CostsResponse {
  rows: UsageRow[];
  total: UsageRow;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    // FastAPI's HTTPException bodies are {"detail": "..."} -- surface that
    // instead of a bare status code so form errors are actually readable.
    const body = await response.json().catch(() => null);
    const detail = body && typeof body === "object" && "detail" in body ? String(body.detail) : null;
    throw new Error(detail ?? `${path} -> HTTP ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function postJSON<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export interface CreatePaperInput {
  slug: string;
  title: string;
  keywords: string[];
  abstract: string | null;
}

export interface ImportPaperInput {
  slug: string;
  title: string | null;
  full_text: string;
  bibliography: string | null;
}

export const api = {
  listPapers: () => request<PaperSummary[]>("/api/papers"),
  createPaper: (input: CreatePaperInput) => postJSON<PaperSummary>("/api/papers", input),
  importPaper: (input: ImportPaperInput) =>
    postJSON<{ status: string }>(`/api/papers/${input.slug}/import`, input),
  getPaper: (slug: string) => request<PaperDetail>(`/api/papers/${slug}`),
  getFlow: (slug: string) => request<FlowStatus>(`/api/papers/${slug}/flow`),
  getProvenance: (slug: string) => request<ProvenanceEntry[]>(`/api/papers/${slug}/provenance`),
  getCosts: (slug: string) => request<CostsResponse>(`/api/papers/${slug}/costs`),
  getArtifact: (slug: string, path: string) =>
    request<{ path: string; content: string }>(`/api/papers/${slug}/artifacts/${path}`),
  triggerRun: (slug: string, phase?: string) => postJSON<{ status: string }>(`/api/papers/${slug}/run`, { phase: phase ?? null }),
  respondToGate: (slug: string, response: Record<string, unknown>) =>
    postJSON<{ status: string }>(`/api/papers/${slug}/respond`, response),
};
