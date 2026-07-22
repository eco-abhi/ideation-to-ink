import { useState, type CSSProperties } from "react";
import type { FlowStatus, ProvenanceEntry } from "../api";

interface Props {
  flow: FlowStatus;
  selectedNodeId: string | null;
  provenance: ProvenanceEntry[];
  onRespond: (response: Record<string, unknown>) => void;
  onSubmitResults: (resultsText: string, notes: string) => void;
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
export function GatePanel({ flow, selectedNodeId, provenance, onRespond, onSubmitResults, responding }: Props) {
  if (!selectedNodeId) {
    return <p style={hintStyle}>Click a node in the graph for detail.</p>;
  }

  if (selectedNodeId === flow.paused_gate && flow.gate_payload) {
    const payload = flow.gate_payload;

    if (payload.type === "awaiting_experiment_results") {
      return (
        <div>
          <h4 style={{ margin: "0 0 8px", color: "var(--status-warning)" }}>⏸ Paused: awaiting_experiment_results</h4>
          <ResultsForm onSubmit={onSubmitResults} responding={responding} />
          <p style={{ ...hintStyle, marginTop: 10 }}>
            Already wrote <code>experiments/results/metrics.json</code> yourself?
          </p>
          <button disabled={responding} onClick={() => onRespond({ ack: true })}>
            {responding ? "Working..." : "Continue (results are ready)"}
          </button>
        </div>
      );
    }

    if (payload.type === "human_review_feedback") {
      const major = Array.isArray(payload.major_concerns) ? (payload.major_concerns as string[]) : [];
      const minor = Array.isArray(payload.minor_concerns) ? (payload.minor_concerns as string[]) : [];
      return (
        <div>
          <h4 style={{ margin: "0 0 8px", color: "var(--status-warning)" }}>
            ⏸ Paused: your feedback (round {String(payload.round)})
          </h4>
          {major.length > 0 && (
            <>
              <p style={{ fontSize: 12, fontWeight: 600, margin: "0 0 4px" }}>Automated reviewers' major concerns</p>
              <ul style={concernListStyle}>
                {major.map((m, i) => (
                  <li key={i}>{m}</li>
                ))}
              </ul>
            </>
          )}
          {minor.length > 0 && (
            <>
              <p style={{ fontSize: 12, fontWeight: 600, margin: "8px 0 4px" }}>Minor concerns</p>
              <ul style={concernListStyle}>
                {minor.map((m, i) => (
                  <li key={i}>{m}</li>
                ))}
              </ul>
            </>
          )}
          {major.length === 0 && minor.length === 0 && (
            <p style={hintStyle}>The automated reviewers raised no concerns this round.</p>
          )}
          <ReviewFeedbackForm onRespond={onRespond} responding={responding} />
        </div>
      );
    }

    const actions = quickActionsFor(payload);
    return (
      <div>
        <h4 style={{ margin: "0 0 8px", color: "var(--status-warning)" }}>⏸ Paused: {String(payload.type)}</h4>
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
          <p style={hintStyle}>
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
    return <p style={hintStyle}>No provenance recorded for this node yet.</p>;
  }

  // model/cost_usd are both null in two very different situations: a genuinely
  // deterministic node that never calls an LLM (e.g. experiment_scaffolder), or
  // a node that DID attempt a call but errored before NodeResult was ever built
  // (traced_node's except-branch logs model=None on any exception). latest.error
  // is what tells them apart -- don't claim "deterministic" when it just failed.
  const modelLabel = latest.model ?? (latest.error ? "(failed before a model call completed)" : "(deterministic, no LLM call)");
  const costLabel =
    latest.cost_usd !== null
      ? `$${latest.cost_usd.toFixed(4)}`
      : latest.error
        ? "n/a (failed)"
        : latest.model
          ? "unknown (no pricing data)"
          : "n/a";

  return (
    <div>
      <h4 style={{ margin: "0 0 8px" }}>{latest.agent}</h4>
      <dl style={dlStyle}>
        <dt>Model</dt>
        <dd>{modelLabel}</dd>
        <dt>Skill</dt>
        <dd>{latest.skill_name ? `${latest.skill_name} @ ${latest.skill_upstream_commit?.slice(0, 8)}` : "(local)"}</dd>
        <dt>Tokens</dt>
        <dd>
          {latest.tokens.prompt ?? 0} prompt / {latest.tokens.completion ?? 0} completion
        </dd>
        <dt>Cost</dt>
        <dd>{costLabel}</dd>
        <dt>Duration</dt>
        <dd>{latest.duration_ms}ms</dd>
        <dt>Artifacts</dt>
        <dd>{latest.artifacts_written.length ? latest.artifacts_written.join(", ") : "none"}</dd>
      </dl>
      {latest.error ? (
        <p style={{ color: "var(--status-critical)", fontSize: 12 }}>Error: {latest.error}</p>
      ) : (
        <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>{latest.output_summary}</p>
      )}
      {entries.length > 1 && (
        <p style={{ fontSize: 11, color: "var(--text-muted)" }}>
          Ran {entries.length} times (revision loop) -- showing the latest.
        </p>
      )}
    </div>
  );
}

function ResultsForm({
  onSubmit,
  responding,
}: {
  onSubmit: (resultsText: string, notes: string) => void;
  responding: boolean;
}) {
  const [resultsText, setResultsText] = useState("");
  const [notes, setNotes] = useState("");
  const canSubmit = resultsText.trim().length > 0 && !responding;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label style={formLabelStyle}>
        Results (metrics, numbers, or a pasted table — whatever you've got)
        <textarea
          value={resultsText}
          onChange={(e) => setResultsText(e.target.value)}
          rows={6}
          style={textareaStyle}
          placeholder={'{"accuracy": 0.91, "baseline": 0.84, ...} or plain text -- read as-is'}
        />
      </label>
      <label style={formLabelStyle}>
        Notes (optional)
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          style={textareaStyle}
          placeholder="anything worth flagging -- an outlier seed, a caveat, etc."
        />
      </label>
      <button disabled={!canSubmit} onClick={() => onSubmit(resultsText, notes)}>
        {responding ? "Working..." : "Submit results"}
      </button>
    </div>
  );
}

function ReviewFeedbackForm({
  onRespond,
  responding,
}: {
  onRespond: (response: Record<string, unknown>) => void;
  responding: boolean;
}) {
  const [feedback, setFeedback] = useState("");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
      <label style={formLabelStyle}>
        Your feedback (optional — merged in as another major concern if you add any)
        <textarea
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          rows={4}
          style={textareaStyle}
          placeholder="e.g. the related-work section still misses the 2024 baseline"
        />
      </label>
      <div style={{ display: "flex", gap: 6 }}>
        <button disabled={responding} onClick={() => onRespond({ ack: true })} style={{ flex: 1 }}>
          {responding ? "Working..." : "Approve as-is"}
        </button>
        <button
          disabled={responding || !feedback.trim()}
          onClick={() => onRespond({ feedback: feedback.trim() })}
          style={{ flex: 1 }}
        >
          {responding ? "Working..." : "Submit feedback"}
        </button>
      </div>
    </div>
  );
}

const hintStyle: CSSProperties = { color: "var(--text-muted)", fontSize: 13 };

const formLabelStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  fontSize: 12,
  color: "var(--text-secondary)",
};

const textareaStyle: CSSProperties = {
  fontFamily: "ui-monospace, Consolas, monospace",
  fontSize: 12,
  padding: 6,
  borderRadius: 6,
  border: "1px solid var(--gridline)",
  background: "var(--page-plane)",
  color: "var(--text-primary)",
  resize: "vertical",
};

const concernListStyle: CSSProperties = {
  margin: 0,
  paddingLeft: 18,
  fontSize: 12,
  color: "var(--text-secondary)",
};

const preStyle: CSSProperties = {
  background: "var(--page-plane)",
  border: "1px solid var(--gridline)",
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
  color: "var(--status-critical)",
  borderColor: "var(--status-critical)",
};
