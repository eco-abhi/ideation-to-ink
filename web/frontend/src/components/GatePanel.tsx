import type { CSSProperties } from "react";
import type { FlowStatus, ProvenanceEntry } from "../api";

interface Props {
  flow: FlowStatus;
  selectedNodeId: string | null;
  provenance: ProvenanceEntry[];
}

// Doubles as the node-detail panel: shows the paused gate's payload if the
// selected node is the currently-paused gate, otherwise the selected node's
// latest provenance entry, otherwise a hint to click a node.
export function GatePanel({ flow, selectedNodeId, provenance }: Props) {
  if (!selectedNodeId) {
    return <p style={{ color: "#64748b", fontSize: 13 }}>Click a node in the graph for detail.</p>;
  }

  if (selectedNodeId === flow.paused_gate && flow.gate_payload) {
    const payload = flow.gate_payload;
    return (
      <div>
        <h4 style={{ margin: "0 0 8px" }}>⏸ Paused: {String(payload.type)}</h4>
        <pre style={preStyle}>{JSON.stringify(payload, null, 2)}</pre>
        <p style={{ fontSize: 12, color: "#64748b" }}>
          Respond via <code>papers/&lt;slug&gt;/HUMAN_RESPONSE.json</code> + <code>engine run --resume</code>{" "}
          (gate-response actions from this UI aren't wired up yet).
        </p>
      </div>
    );
  }

  const entries = provenance.filter((e) => e.agent === selectedNodeId);
  const latest = entries[entries.length - 1];
  if (!latest) {
    return <p style={{ color: "#64748b", fontSize: 13 }}>No provenance recorded for this node yet.</p>;
  }

  return (
    <div>
      <h4 style={{ margin: "0 0 8px" }}>{latest.agent}</h4>
      <dl style={dlStyle}>
        <dt>Model</dt>
        <dd>{latest.model ?? "(deterministic, no LLM call)"}</dd>
        <dt>Skill</dt>
        <dd>{latest.skill_name ? `${latest.skill_name} @ ${latest.skill_upstream_commit?.slice(0, 8)}` : "(local)"}</dd>
        <dt>Tokens</dt>
        <dd>
          {latest.tokens.prompt ?? 0} prompt / {latest.tokens.completion ?? 0} completion
        </dd>
        <dt>Cost</dt>
        <dd>{latest.cost_usd !== null ? `$${latest.cost_usd.toFixed(4)}` : "unknown"}</dd>
        <dt>Duration</dt>
        <dd>{latest.duration_ms}ms</dd>
        <dt>Artifacts</dt>
        <dd>{latest.artifacts_written.length ? latest.artifacts_written.join(", ") : "none"}</dd>
      </dl>
      {latest.error ? (
        <p style={{ color: "#dc2626", fontSize: 12 }}>Error: {latest.error}</p>
      ) : (
        <p style={{ fontSize: 12, color: "#475569" }}>{latest.output_summary}</p>
      )}
      {entries.length > 1 && (
        <p style={{ fontSize: 11, color: "#94a3b8" }}>
          Ran {entries.length} times (revision loop) -- showing the latest.
        </p>
      )}
    </div>
  );
}

const preStyle: CSSProperties = {
  background: "#f8fafc",
  padding: 8,
  borderRadius: 6,
  fontSize: 11,
  overflowX: "auto",
};

const dlStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "auto 1fr",
  gap: "4px 12px",
  fontSize: 12,
  margin: 0,
};
