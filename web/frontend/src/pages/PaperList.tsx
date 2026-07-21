import { useEffect, useState, type CSSProperties, type FormEvent } from "react";
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
  const [slug, setSlug] = useState("");
  const [topic, setTopic] = useState("");
  const [creating, setCreating] = useState(false);

  const refresh = () => {
    api
      .listPapers()
      .then(setPapers)
      .catch((e) => setError(String(e)));
  };

  useEffect(refresh, []);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const created = await api.createPaper(slug.trim(), topic.trim());
      setSlug("");
      setTopic("");
      refresh();
      onSelect(created.paper_id);
    } catch (err) {
      setError(String(err));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div>
      <form onSubmit={handleCreate} style={formStyle}>
        <h3 style={{ margin: "0 0 8px" }}>New paper</h3>
        <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
          <input
            placeholder="slug (e.g. supply-chain-agents)"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required
            pattern="[a-zA-Z0-9][a-zA-Z0-9_-]*"
            title="alphanumeric, then alphanumeric/-/_ only"
            style={inputStyle}
          />
        </div>
        <textarea
          placeholder="Paste the topic / idea for this paper..."
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          required
          rows={3}
          style={{ ...inputStyle, width: "100%", resize: "vertical", marginBottom: 8 }}
        />
        <button type="submit" disabled={creating}>
          {creating ? "Creating..." : "Create paper"}
        </button>
      </form>

      {error && <p style={{ color: "#dc2626" }}>{error}</p>}
      {!papers && <p>Loading...</p>}
      {papers && papers.length === 0 && <p style={{ color: "#64748b" }}>No papers yet -- create one above.</p>}
      {papers && papers.length > 0 && (
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
      )}
    </div>
  );
}

const formStyle: CSSProperties = {
  border: "1px solid #e2e8f0",
  borderRadius: 8,
  padding: 16,
  marginBottom: 24,
  maxWidth: 480,
};

const inputStyle: CSSProperties = {
  padding: 8,
  border: "1px solid #cbd5e1",
  borderRadius: 6,
  fontFamily: "inherit",
  fontSize: 14,
};
