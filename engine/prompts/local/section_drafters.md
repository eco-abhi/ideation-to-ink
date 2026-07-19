## Project-Specific Task: Draft One Section

You are drafting the **{section_name}** section of this paper as a standalone
LaTeX fragment (no `\documentclass`, no `\begin{{document}}`, no preamble).

Topic: {topic}
Research questions:
{research_questions}
Key points to cover in this section:
{key_points}
Target length: ~{target_word_count} words.

## Citations

You do not have a live bibliography yet -- a downstream `citation_verifier` agent
will independently verify every citation you propose against real academic APIs
(arXiv, CrossRef, Semantic Scholar) before anything ships. This means:

- Only cite works you can name with real, specific bibliographic detail (an
  actual title, actual authors, actual year) -- never invent a plausible-sounding
  paper to fill a citation-shaped hole. If you don't know a real source for a
  claim, don't cite one; state the claim without `\cite{{}}` instead, or mark it
  as needing evidence.
- Use `\cite{{key}}` in the LaTeX body with a short, unique bibtex key
  (e.g. `smith2023agentic`), and return the matching citation metadata
  (key, title, authors, year, and doi/arxiv_id ONLY if you actually know it --
  leave them null rather than guessing) in the `citations` field.
- List every load-bearing factual claim you make in this section in the `claims`
  field as plain text (one sentence each), independent of whether it has a
  citation -- this feeds the claims-evidence audit downstream.

Respond with only the JSON object the schema requires.
