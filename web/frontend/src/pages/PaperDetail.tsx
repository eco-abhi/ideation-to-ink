import { useCallback, useEffect, useState } from "react";
import { api, type CostsResponse, type FlowStatus, type PaperDetail as PaperDetailT, type ProvenanceEntry } from "../api";
import { FlowGraph } from "../components/FlowGraph";
import { CostTable } from "../components/CostTable";
import { GatePanel } from "../components/GatePanel";

const POLL_INTERVAL_MS = 3000;

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

  const handleRun = async () => {
    setActionPending(true);
    setError(null);
    try {
      await api.triggerRun(paperId);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setActionPending(false);
    }
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

  return (
    <div>
      <button onClick={onBack} style={{ marginBottom: 12 }}>
        ← All papers
      </button>
      <h2 style={{ margin: "0 0 4px" }}>{paperId}</h2>
      {error && <p style={{ color: "#dc2626" }}>{error}</p>}
      {detail && (
        <p style={{ color: "#64748b", marginTop: 0 }}>
          {detail.topic} — phase <strong>{detail.phase}</strong>
          {detail.running && " (running…)"}
          {detail.paused && " (paused, waiting on a decision)"}
          {detail.revision_loop_count > 0 && ` — revision loop ${detail.revision_loop_count}/3`}
        </p>
      )}
      {canRun && (
        <button onClick={handleRun} disabled={actionPending} style={{ marginBottom: 12 }}>
          {actionPending ? "Starting..." : detail?.status === "new" ? "Run pipeline" : "Continue run"}
        </button>
      )}
      {detail?.running && <p style={{ color: "#f59e0b", fontSize: 13 }}>Running in the background — this page polls every 3s.</p>}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 16 }}>
        <div>{flow && <FlowGraph flow={flow} selectedNodeId={selectedNodeId} onSelectNode={setSelectedNodeId} />}</div>
        <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: 12 }}>
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

      <h3>Cost & Usage</h3>
      {costs && <CostTable costs={costs} />}
    </div>
  );
}
