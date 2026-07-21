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
  topic: string;
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

async function getJSON<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${path} -> HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  listPapers: () => getJSON<PaperSummary[]>("/api/papers"),
  getPaper: (slug: string) => getJSON<PaperDetail>(`/api/papers/${slug}`),
  getFlow: (slug: string) => getJSON<FlowStatus>(`/api/papers/${slug}/flow`),
  getProvenance: (slug: string) => getJSON<ProvenanceEntry[]>(`/api/papers/${slug}/provenance`),
  getCosts: (slug: string) => getJSON<CostsResponse>(`/api/papers/${slug}/costs`),
  getArtifact: (slug: string, path: string) =>
    getJSON<{ path: string; content: string }>(`/api/papers/${slug}/artifacts/${path}`),
};
