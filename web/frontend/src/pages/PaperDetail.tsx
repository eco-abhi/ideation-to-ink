import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { api, type CostsResponse, type FlowStatus, type PaperDetail as PaperDetailT, type ProvenanceEntry } from "../api";
import { FlowGraph } from "../components/FlowGraph";
import { CostTable } from "../components/CostTable";
import { GatePanel } from "../components/GatePanel";

const POLL_INTERVAL_MS = 3000;
const ABSTRACT_COLLAPSE_LENGTH = 260;
const SIDEBAR_WIDTH = 360; // tuned for a laptop viewport (~1280-1440px) alongside a max-width: 1180 shell

// Matches PHASE_ENTRY's user-restartable keys in engine/graphs/master.py --
// "revision" (mid-loop) and "done" (nothing to re-enter) aren't valid targets.
const RERUN_PHASES = ["ideation", "experiments", "writing", "review"] as const;

interface Props {
  paperId: string;
  onBack: () => void;
}

export function PaperDetail({ paperId, onBack }: Props) {
  const [detail, setDetail] = useState<PaperDetailT | null>(null);
  const [flow, setFlow] = useState<FlowStatus | null>(null);
  const [costs, setCosts] = useState<CostsResponse | null>(null);
  const [provenance, setProvenance] = useState<ProvenanceEntry[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [rerunPhase, setRerunPhase] = useState<(typeof RERUN_PHASES)[number]>("ideation");

  const refresh = useCallback(() => {
    return Promise.all([api.getPaper(paperId), api.getFlow(paperId), api.getCosts(paperId), api.getProvenance(paperId)])
      .then(([d, f, c, p]) => {
        setDetail(d);
        setFlow(f);
        setCosts(c);
        setProvenance(p);
        setError(null);
      })
      .catch((e) => setError(String(e)));
  }, [paperId]);

  useEffect(() => {
    let cancelled = false;
    const tick = () => !cancelled && refresh();
    tick();
    const interval = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [refresh]);

  // Jump to the actionable node the moment a run pauses, instead of leaving
  // the graph on "click a node for detail" (or worse, whatever unrelated node
  // was selected before) with the real action buttons one extra click away.
  // Keyed on the *value* of paused_gate, not the flow object -- refresh() makes
  // a new object every poll, but this should only fire on an actual new pause,
  // not re-steal a selection the user deliberately clicked elsewhere.
  useEffect(() => {
    if (flow?.paused_gate) setSelectedNodeId(flow.paused_gate);
  }, [flow?.paused_gate]);

  const runWithPhase = async (phase?: string) => {
    setActionPending(true);
    setError(null);
    try {
      await api.triggerRun(paperId, phase);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setActionPending(false);
    }
  };

  const handleRun = () => runWithPhase();

  const handleRerun = () => {
    const confirmed = window.confirm(
      `Force entry at "${rerunPhase}" and re-run from there? This re-executes agents (real API calls/cost) ` +
        `and can overwrite that phase's artifacts. Later-phase results already on disk aren't cleared automatically.`,
    );
    if (confirmed) void runWithPhase(rerunPhase);
  };

  const handleRespond = async (response: Record<string, unknown>) => {
    setActionPending(true);
    setError(null);
    try {
      await api.respondToGate(paperId, response);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setActionPending(false);
    }
  };

  const canRun = detail && !detail.running && !detail.paused && detail.phase !== "done";
  const canRerun = detail && !detail.running;

  return (
    <div>
      <button onClick={onBack} style={{ marginBottom: 16 }}>
        ← All papers
      </button>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <h2 style={{ margin: 0, fontFamily: "ui-monospace, Consolas, monospace", fontSize: 18 }}>{paperId}</h2>
          <StatusPill detail={detail} />
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
          {canRun && (
            <button onClick={handleRun} disabled={actionPending}>
              {actionPending ? "Starting..." : detail?.status === "new" ? "Run pipeline" : "Continue run"}
            </button>
          )}
          {canRerun && (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Rerun from:</span>
              <select value={rerunPhase} onChange={(e) => setRerunPhase(e.target.value as typeof rerunPhase)}>
                {RERUN_PHASES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
              <button onClick={handleRerun} disabled={actionPending}>
                {actionPending ? "Starting..." : "Rerun"}
              </button>
            </div>
          )}
        </div>
      </div>

      {error && <p style={{ color: "var(--status-critical)", fontSize: 13 }}>{error}</p>}

      {/* Side-by-side for a laptop screen: graph gets the remaining space, the
          sidebar (paper attributes + node/gate detail) holds a fixed comfortable
          width instead of squeezing into a narrower fraction. */}
      <div style={{ display: "grid", gridTemplateColumns: `1fr ${SIDEBAR_WIDTH}px`, gap: 16, alignItems: "start" }}>
        <div>{flow && <FlowGraph flow={flow} selectedNodeId={selectedNodeId} onSelectNode={setSelectedNodeId} />}</div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <PaperAttributes detail={detail} />

          <div style={cardStyle}>
            {flow?.paused_gate && selectedNodeId !== flow.paused_gate && (
              <button
                onClick={() => setSelectedNodeId(flow.paused_gate)}
                style={{ marginBottom: 12, width: "100%", borderColor: "var(--status-warning)", color: "var(--status-warning)" }}
              >
                ⏸ Paused at {flow.paused_gate} — respond
              </button>
            )}
            {flow && (
              <GatePanel
                flow={flow}
                selectedNodeId={selectedNodeId}
                provenance={provenance}
                onRespond={handleRespond}
                responding={actionPending}
              />
            )}
          </div>
        </div>
      </div>

      <h3 style={{ marginTop: 24 }}>Cost & Usage</h3>
      <div style={cardStyle}>{costs && <CostTable costs={costs} />}</div>
    </div>
  );
}

function PaperAttributes({ detail }: { detail: PaperDetailT | null }) {
  const [expanded, setExpanded] = useState(false);
  if (!detail) return null;

  const abstract = detail.abstract ?? "";
  const isLong = abstract.length > ABSTRACT_COLLAPSE_LENGTH;
  const shown = isLong && !expanded ? abstract.slice(0, ABSTRACT_COLLAPSE_LENGTH).trimEnd() + "…" : abstract;

  return (
    <div style={cardStyle}>
      <h4 style={{ margin: "0 0 8px", fontSize: 13, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5 }}>
        Paper
      </h4>
      <p style={{ margin: "0 0 10px", fontSize: 14, fontWeight: 600 }}>{detail.title}</p>

      {detail.keywords.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
          {detail.keywords.map((k) => (
            <span
              key={k}
              style={{
                fontSize: 11,
                color: "var(--text-secondary)",
                border: "1px solid var(--gridline)",
                borderRadius: 999,
                padding: "2px 8px",
              }}
            >
              {k}
            </span>
          ))}
        </div>
      )}

      {abstract ? (
        <p style={{ fontSize: 12, color: "var(--text-secondary)", whiteSpace: "pre-wrap", margin: 0 }}>
          {shown}
          {isLong && (
            <button onClick={() => setExpanded((v) => !v)} style={{ marginLeft: 6, padding: "1px 6px", fontSize: 10 }}>
              {expanded ? "Show less" : "Show more"}
            </button>
          )}
        </p>
      ) : (
        <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>No abstract provided.</p>
      )}

      {detail.revision_loop_count > 0 && (
        <p style={{ fontSize: 12, color: "var(--status-warning)", margin: "10px 0 0" }}>
          Revision loop {detail.revision_loop_count}/3
        </p>
      )}
    </div>
  );
}

function StatusPill({ detail }: { detail: PaperDetailT | null }) {
  if (!detail) return null;
  if (detail.running) return <Pill color="var(--series-blue)" label="Running…" />;
  if (detail.paused) return <Pill color="var(--status-warning)" label="Paused" />;
  if (detail.phase === "done") return <Pill color="var(--status-good)" label="Done" />;
  return <Pill color="var(--text-muted)" label={detail.phase} />;
}

function Pill({ color, label }: { color: string; label: string }) {
  return (
    <span
      style={{
        color,
        border: `1px solid ${color}`,
        borderRadius: 999,
        padding: "2px 10px",
        fontSize: 12,
        fontWeight: 600,
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}

const cardStyle: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 8,
  background: "var(--surface-1)",
  padding: 16,
};
