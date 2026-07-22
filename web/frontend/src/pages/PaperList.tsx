import { useEffect, useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import { api, type PaperSummary } from "../api";

const MAX_TITLE_LENGTH = 300; // mirrors web/backend/app.py's MAX_TITLE_LENGTH

type Tab = "new" | "import";

export function PaperList({ onSelect }: { onSelect: (paperId: string) => void }) {
  const [papers, setPapers] = useState<PaperSummary[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("new");

  const refresh = () => {
    api
      .listPapers()
      .then(setPapers)
      .catch((e) => setListError(String(e)));
  };

  useEffect(refresh, []);

  const handleCreated = (paperId: string) => {
    refresh();
    onSelect(paperId);
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 4, marginBottom: 12 }}>
        <TabButton active={tab === "new"} onClick={() => setTab("new")}>
          New paper
        </TabButton>
        <TabButton active={tab === "import"} onClick={() => setTab("import")}>
          Import existing paper
        </TabButton>
      </div>

      {tab === "new" ? <NewPaperForm onCreated={handleCreated} /> : <ImportPaperForm onImportStarted={handleCreated} />}

      {listError && <p style={{ color: "var(--status-critical)" }}>{listError}</p>}
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

function NewPaperForm({ onCreated }: { onCreated: (paperId: string) => void }) {
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [keywords, setKeywords] = useState("");
  const [abstract, setAbstract] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
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
      onCreated(created.paper_id);
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={formStyle}>
      <p style={{ margin: "0 0 12px", fontSize: 12, color: "var(--text-muted)" }}>
        Starting from an idea, not a draft yet -- the pipeline runs ideation → experiments → writing → review from scratch.
      </p>

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

      <Field
        label="Title"
        hint={`Short -- used as a literal literature-search query, so keep it under ${MAX_TITLE_LENGTH} characters. Not the place for the abstract.`}
      >
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

      {error && <p style={{ color: "var(--status-critical)", fontSize: 12 }}>{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? "Creating..." : "Create paper"}
      </button>
    </form>
  );
}

type ImportSource = "paste" | "file";
const ACCEPTED_FILE_EXTENSIONS = ".pdf,.docx";

function ImportPaperForm({ onImportStarted }: { onImportStarted: (paperId: string) => void }) {
  const [source, setSource] = useState<ImportSource>("paste");
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [fullText, setFullText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [bibliography, setBibliography] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setSlug("");
    setTitle("");
    setFullText("");
    setFile(null);
    setBibliography("");
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const startedSlug = slug.trim();
    try {
      if (source === "paste") {
        await api.importPaper({
          slug: startedSlug,
          title: title.trim() || null,
          full_text: fullText,
          bibliography: bibliography.trim() || null,
        });
      } else {
        if (!file) throw new Error("choose a PDF or .docx file");
        await api.importPaperFile({
          slug: startedSlug,
          file,
          title: title.trim() || null,
          bibliography: bibliography.trim() || null,
        });
      }
      reset();
      onImportStarted(startedSlug);
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={formStyle}>
      <p style={{ margin: "0 0 12px", fontSize: 12, color: "var(--text-muted)" }}>
        Already have a draft? Import it here for retroactive review -- citation verification, unsupported-claim
        detection, and structural drift, all against what you already wrote. This runs several real LLM calls in the
        background and can take a minute or two; you'll land on the paper's page and it'll update as it goes.
      </p>

      <div style={{ display: "flex", gap: 12, marginBottom: 12, fontSize: 13 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
          <input type="radio" checked={source === "paste"} onChange={() => setSource("paste")} /> Paste text
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
          <input type="radio" checked={source === "file"} onChange={() => setSource("file")} /> Upload PDF / .docx
        </label>
      </div>

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

      <Field label="Title" hint="Optional -- inferred from the source if omitted, but that fallback is just the slug.">
        <input
          placeholder="The paper's actual title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          style={inputStyle}
        />
      </Field>

      {source === "paste" ? (
        <Field
          label="Full paper text"
          hint="Paste the whole thing. Long pastes are automatically split into chunks so the whole paper gets reviewed, not just the first page."
        >
          <textarea
            placeholder="Paste the complete draft -- title, abstract, all sections..."
            value={fullText}
            onChange={(e) => setFullText(e.target.value)}
            required
            rows={10}
            style={{ ...inputStyle, width: "100%", resize: "vertical", fontFamily: "ui-monospace, Consolas, monospace", fontSize: 12 }}
          />
        </Field>
      ) : (
        <Field
          label="File"
          hint="PDF or .docx, up to 20MB. Legacy .doc isn't supported -- save as .docx first. Scanned/image-only PDFs won't work (no OCR) -- use Paste text instead for those."
        >
          <input
            type="file"
            accept={ACCEPTED_FILE_EXTENSIONS}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            required
            style={inputStyle}
          />
        </Field>
      )}

      <Field label="Bibliography (optional)" hint="BibTeX format (.bib content). Plain reference-list text won't parse -- skip this if you don't have real BibTeX; citation verification just won't run.">
        <textarea
          placeholder={"@article{key2023,\n  title = {...},\n  ...\n}"}
          value={bibliography}
          onChange={(e) => setBibliography(e.target.value)}
          rows={4}
          style={{ ...inputStyle, width: "100%", resize: "vertical", fontFamily: "ui-monospace, Consolas, monospace", fontSize: 12 }}
        />
      </Field>

      {error && <p style={{ color: "var(--status-critical)", fontSize: 12 }}>{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? "Starting import..." : "Import & review"}
      </button>
    </form>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        borderBottom: active ? "2px solid var(--series-blue)" : "2px solid transparent",
        borderRadius: 0,
        borderTop: "none",
        borderLeft: "none",
        borderRight: "none",
        background: "transparent",
        color: active ? "var(--text-primary)" : "var(--text-muted)",
        fontWeight: active ? 600 : 400,
        padding: "6px 4px",
      }}
    >
      {children}
    </button>
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
  maxWidth: 560,
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
