import { useEffect, useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import { api, type PaperSummary } from "../api";

const MAX_TITLE_LENGTH = 300; // mirrors web/backend/app.py's MAX_TITLE_LENGTH

export function PaperList({ onSelect }: { onSelect: (paperId: string) => void }) {
  const [papers, setPapers] = useState<PaperSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [keywords, setKeywords] = useState("");
  const [abstract, setAbstract] = useState("");
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
      const created = await api.createPaper({
        slug: slug.trim(),
        title: title.trim(),
        keywords: keywords
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean),
        abstract: abstract.trim() || null,
      });
      setSlug("");
      setTitle("");
      setKeywords("");
      setAbstract("");
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

        <Field label="Slug">
          <input
            placeholder="supply-chain-agents"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required
            pattern="[a-zA-Z0-9][a-zA-Z0-9_-]*"
            title="alphanumeric, then alphanumeric/-/_ only"
            style={inputStyle}
          />
        </Field>

        <Field label="Title" hint={`Short -- used as a literal literature-search query, so keep it under ${MAX_TITLE_LENGTH} characters. Not the place for the abstract.`}>
          <input
            placeholder="Criticality-Conditioned Schedule Compliance Prediction..."
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            maxLength={MAX_TITLE_LENGTH}
            style={inputStyle}
          />
          <span style={{ fontSize: 11, color: title.length > MAX_TITLE_LENGTH * 0.9 ? "var(--status-warning)" : "var(--text-muted)" }}>
            {title.length}/{MAX_TITLE_LENGTH}
          </span>
        </Field>

        <Field label="Keywords" hint="Comma-separated. Feeds search-query expansion, not sent to any API as-is.">
          <input
            placeholder="ABC classification, compliance prediction, graph attention networks"
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            style={inputStyle}
          />
        </Field>

        <Field label="Abstract" hint="Paste as much as you want -- this is context for the pipeline's LLM calls, never a literal search query.">
          <textarea
            placeholder="Paste the full abstract / idea description here..."
            value={abstract}
            onChange={(e) => setAbstract(e.target.value)}
            rows={5}
            style={{ ...inputStyle, width: "100%", resize: "vertical" }}
          />
        </Field>

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
              <th style={thStyle}>Title</th>
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
                  {p.title}
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

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label style={{ display: "block", marginBottom: 12 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>{label}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, width: "100%" }}>{children}</div>
      {hint && <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3 }}>{hint}</div>}
    </label>
  );
}

const formStyle: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 8,
  background: "var(--surface-1)",
  padding: 16,
  marginBottom: 24,
  maxWidth: 520,
};

const inputStyle: CSSProperties = {
  padding: 8,
  border: "1px solid var(--gridline)",
  borderRadius: 6,
  fontFamily: "inherit",
  fontSize: 14,
  flex: 1,
};

const thStyle: CSSProperties = { padding: 8, fontSize: 12, color: "var(--text-muted)", fontWeight: 600 };
const tdStyle: CSSProperties = { padding: 8, fontSize: 13 };
const rowStyle: CSSProperties = { cursor: "pointer", borderBottom: "1px solid var(--gridline)" };
