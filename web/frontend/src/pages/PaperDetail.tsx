import { useEffect, useState } from "react";
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

  useEffect(() => {
    let cancelled = false;

    const refresh = () => {
      Promise.all([
        api.getPaper(paperId),
        api.getFlow(paperId),
        api.getCosts(paperId),
        api.getProvenance(paperId),
      ])
        .then(([d, f, c, p]) => {
          if (cancelled) return;
          setDetail(d);
          setFlow(f);
          setCosts(c);
          setProvenance(p);
          setError(null);
        })
        .catch((e) => !cancelled && setError(String(e)));
    };

    refresh();
    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [paperId]);

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
          {detail.paused && " (paused)"}
          {detail.revision_loop_count > 0 && ` — revision loop ${detail.revision_loop_count}/3`}
        </p>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 16 }}>
        <div>{flow && <FlowGraph flow={flow} selectedNodeId={selectedNodeId} onSelectNode={setSelectedNodeId} />}</div>
        <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: 12 }}>
          {flow && <GatePanel flow={flow} selectedNodeId={selectedNodeId} provenance={provenance} />}
        </div>
      </div>

      <h3>Cost & Usage</h3>
      {costs && <CostTable costs={costs} />}
    </div>
  );
}
