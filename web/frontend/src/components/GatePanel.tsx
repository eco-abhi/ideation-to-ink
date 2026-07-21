import type { CSSProperties } from "react";
import type { FlowStatus, ProvenanceEntry } from "../api";

interface Props {
  flow: FlowStatus;
  selectedNodeId: string | null;
  provenance: ProvenanceEntry[];
  onRespond: (response: Record<string, unknown>) => void;
  responding: boolean;
}

interface QuickAction {
  label: string;
  response: Record<string, unknown>;
  danger?: boolean;
}

// Every gate's expected resume shape, straight from the payloads written by
// engine/graphs/{ideation,experiments,writing,review}.py and _registry.py's
// error_gate. Keep in sync if a gate's instructions change.
function quickActionsFor(payload: Record<string, unknown>): QuickAction[] {
  switch (payload.type) {
    case "novelty_verdict":
      return [
        { label: "Proceed", response: { decision: "proceed" } },
        { label: "Stop", response: { decision: "stop" }, danger: true },
      ];
    case "methodology_approval":
      return [
        { label: "Approve", response: { decision: "approve" } },
        { label: "Revise (stop for manual edit)", response: { decision: "revise" }, danger: true },
      ];
    case "awaiting_experiment_results":
      return [{ label: "Continue (results are ready)", response: { ack: true } }];
    case "suspicious_citations": {
      const suspicious = Array.isArray(payload.suspicious) ? payload.suspicious : [];
      const keys = suspicious.map((s) => (s as { bib_key?: string }).bib_key).filter(Boolean);
      return [
        { label: "Approve none (exclude all)", response: { approve: [] } },
        { label: `Approve all (${keys.length})`, response: { approve: keys } },
      ];
    }
    case "revision_cap_reached":
      return [
        { label: "Force done (accept as-is)", response: { decision: "force_done" } },
        { label: "Abandon (manual intervention)", response: { decision: "abandon" }, danger: true },
      ];
    case "node_error":
      return [{ label: "Acknowledge & retry", response: { ack: true } }];
    default:
      return [];
  }
}

// Doubles as the node-detail panel: shows the paused gate's payload + response
// actions if the selected node is the currently-paused gate, otherwise the
// selected node's latest provenance entry, otherwise a hint to click a node.
export function GatePanel({ flow, selectedNodeId, provenance, onRespond, responding }: Props) {
  if (!selectedNodeId) {
    return <p style={{ color: "#64748b", fontSize: 13 }}>Click a node in the graph for detail.</p>;
  }

  if (selectedNodeId === flow.paused_gate && flow.gate_payload) {
    const payload = flow.gate_payload;
    const actions = quickActionsFor(payload);
    return (
      <div>
        <h4 style={{ margin: "0 0 8px" }}>⏸ Paused: {String(payload.type)}</h4>
        <pre style={preStyle}>{JSON.stringify(payload, null, 2)}</pre>
        {actions.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
            {actions.map((action) => (
              <button
                key={action.label}
                disabled={responding}
                onClick={() => onRespond(action.response)}
                style={action.danger ? dangerButtonStyle : undefined}
              >
                {responding ? "Working..." : action.label}
              </button>
            ))}
          </div>
        ) : (
          <p style={{ fontSize: 12, color: "#64748b" }}>
            Unrecognized gate type -- respond via <code>HUMAN_RESPONSE.json</code> + <code>engine run --resume</code>{" "}
            instead.
          </p>
        )}
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

const dangerButtonStyle: CSSProperties = {
  color: "#b91c1c",
  borderColor: "#fca5a5",
};
