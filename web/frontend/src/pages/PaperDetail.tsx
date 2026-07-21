import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { api, type CostsResponse, type FlowStatus, type PaperDetail as PaperDetailT, type ProvenanceEntry } from "../api";
import { FlowGraph } from "../components/FlowGraph";
import { CostTable } from "../components/CostTable";
import { GatePanel } from "../components/GatePanel";

const POLL_INTERVAL_MS = 3000;
const TOPIC_COLLAPSE_LENGTH = 220;

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
  const [topicExpanded, setTopicExpanded] = useState(false);

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

  const topic = detail?.topic ?? "";
  const topicIsLong = topic.length > TOPIC_COLLAPSE_LENGTH;
  const topicShown = topicIsLong && !topicExpanded ? topic.slice(0, TOPIC_COLLAPSE_LENGTH).trimEnd() + "…" : topic;

  return (
    <div>
      <button onClick={onBack} style={{ marginBottom: 16 }}>
        ← All papers
      </button>

      <div style={cardStyle}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <h2 style={{ margin: 0, fontFamily: "ui-monospace, Consolas, monospace", fontSize: 18 }}>{paperId}</h2>
          <StatusPill detail={detail} />
        </div>

        {error && <p style={{ color: "var(--status-critical)", fontSize: 13 }}>{error}</p>}

        {detail && (
          <>
            <p style={{ color: "var(--text-secondary)", fontSize: 14, margin: "10px 0", whiteSpace: "pre-wrap" }}>
              {topicShown}
              {topicIsLong && (
                <button
                  onClick={() => setTopicExpanded((v) => !v)}
                  style={{ marginLeft: 8, padding: "2px 8px", fontSize: 11, verticalAlign: "middle" }}
                >
                  {topicExpanded ? "Show less" : "Show more"}
                </button>
              )}
            </p>
            {detail.revision_loop_count > 0 && (
              <p style={{ fontSize: 12, color: "var(--status-warning)", margin: "0 0 8px" }}>
                Revision loop {detail.revision_loop_count}/3
              </p>
            )}
          </>
        )}

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

      <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 16, marginTop: 16 }}>
        <div>{flow && <FlowGraph flow={flow} selectedNodeId={selectedNodeId} onSelectNode={setSelectedNodeId} />}</div>
        <div style={{ ...cardStyle, margin: 0, alignSelf: "start" }}>
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

      <h3 style={{ marginTop: 24 }}>Cost & Usage</h3>
      <div style={cardStyle}>{costs && <CostTable costs={costs} />}</div>
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
