import { useEffect, useState } from "react";
import { api, type PaperSummary } from "../api";

const PHASE_COLOR: Record<string, string> = {
  ideation: "#3b82f6",
  experiments: "#8b5cf6",
  writing: "#f59e0b",
  review: "#10b981",
  revision: "#f97316",
  done: "#22c55e",
};

interface Props {
  onSelect: (paperId: string) => void;
}

export function PaperList({ onSelect }: Props) {
  const [papers, setPapers] = useState<PaperSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listPapers()
      .then(setPapers)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <p style={{ color: "#dc2626" }}>{error}</p>;
  if (!papers) return <p>Loading...</p>;
  if (papers.length === 0) {
    return (
      <p style={{ color: "#64748b" }}>
        No papers yet. Run <code>python -m engine new &lt;slug&gt; --topic "..."</code> to scaffold one.
      </p>
    );
  }

  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>
          <th style={{ padding: 8 }}>Slug</th>
          <th style={{ padding: 8 }}>Topic</th>
          <th style={{ padding: 8 }}>Venue</th>
          <th style={{ padding: 8 }}>Phase</th>
          <th style={{ padding: 8 }}>Status</th>
        </tr>
      </thead>
      <tbody>
        {papers.map((p) => (
          <tr
            key={p.paper_id}
            onClick={() => onSelect(p.paper_id)}
            style={{ cursor: "pointer", borderBottom: "1px solid #f1f5f9" }}
          >
            <td style={{ padding: 8, fontFamily: "monospace" }}>{p.paper_id}</td>
            <td style={{ padding: 8 }}>{p.topic}</td>
            <td style={{ padding: 8 }}>{p.venue ?? "—"}</td>
            <td style={{ padding: 8 }}>
              <span
                style={{
                  background: PHASE_COLOR[p.phase] ?? "#94a3b8",
                  color: "white",
                  borderRadius: 4,
                  padding: "2px 8px",
                  fontSize: 12,
                }}
              >
                {p.phase}
              </span>
            </td>
            <td style={{ padding: 8 }}>{p.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
