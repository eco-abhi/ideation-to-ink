import { useEffect, useState, type CSSProperties, type FormEvent } from "react";
import { api, type PaperSummary } from "../api";

export function PaperList({ onSelect }: { onSelect: (paperId: string) => void }) {
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
        <h3 style={{ margin: "0 0 12px", fontSize: 14, color: "var(--text-secondary)" }}>New paper</h3>
        <input
          placeholder="slug (e.g. supply-chain-agents)"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          required
          pattern="[a-zA-Z0-9][a-zA-Z0-9_-]*"
          title="alphanumeric, then alphanumeric/-/_ only"
          style={{ ...inputStyle, display: "block", width: "100%", marginBottom: 8 }}
        />
        <textarea
          placeholder="Paste the topic / idea for this paper..."
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          required
          rows={3}
          style={{ ...inputStyle, width: "100%", resize: "vertical", marginBottom: 10 }}
        />
        <button type="submit" disabled={creating}>
          {creating ? "Creating..." : "Create paper"}
        </button>
      </form>

      {error && <p style={{ color: "var(--status-critical)" }}>{error}</p>}
      {!papers && <p style={{ color: "var(--text-muted)" }}>Loading...</p>}
      {papers && papers.length === 0 && <p style={{ color: "var(--text-muted)" }}>No papers yet -- create one above.</p>}
      {papers && papers.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid var(--gridline)" }}>
              <th style={thStyle}>Slug</th>
              <th style={thStyle}>Topic</th>
              <th style={thStyle}>Venue</th>
              <th style={thStyle}>Phase</th>
              <th style={thStyle}>Status</th>
            </tr>
          </thead>
          <tbody>
            {papers.map((p) => (
              <tr key={p.paper_id} onClick={() => onSelect(p.paper_id)} style={rowStyle}>
                <td style={{ ...tdStyle, fontFamily: "ui-monospace, Consolas, monospace" }}>{p.paper_id}</td>
                <td style={{ ...tdStyle, maxWidth: 420, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {p.topic}
                </td>
                <td style={tdStyle}>{p.venue ?? "—"}</td>
                <td style={tdStyle}>
                  <span
                    style={{
                      border: "1px solid var(--text-muted)",
                      color: "var(--text-secondary)",
                      borderRadius: 999,
                      padding: "1px 8px",
                      fontSize: 12,
                    }}
                  >
                    {p.phase}
                  </span>
                </td>
                <td style={tdStyle}>{p.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const formStyle: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 8,
  background: "var(--surface-1)",
  padding: 16,
  marginBottom: 24,
  maxWidth: 480,
};

const inputStyle: CSSProperties = {
  padding: 8,
  border: "1px solid var(--gridline)",
  borderRadius: 6,
  fontFamily: "inherit",
  fontSize: 14,
};

const thStyle: CSSProperties = { padding: 8, fontSize: 12, color: "var(--text-muted)", fontWeight: 600 };
const tdStyle: CSSProperties = { padding: 8, fontSize: 13 };
const rowStyle: CSSProperties = { cursor: "pointer", borderBottom: "1px solid var(--gridline)" };
