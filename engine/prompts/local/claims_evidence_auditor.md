## Project-Specific Task: Claim-Evidence Audit

Every claim below was extracted verbatim from the manuscript along with whatever
evidence references (bib keys) it cites, plus whether that citation actually
survived independent verification (`citation_verified`). Your job is to judge
whether each claim is actually *supported*, not merely *decorated with a citation*.

- A claim with `citation_verified=False` (no evidence_refs, or every ref failed
  verification) is unsupported by definition -- mark it `unsupported`.
- A claim with a verified citation can still be unsupported if the claim is
  broader or stronger than what a citation could plausibly establish (e.g. a
  single case study cited to support a universal claim).
- Do not be lenient because a citation exists. A citation-shaped decoration is
  not evidence.

Claims:
{claims}

Respond with only the JSON object the schema requires: one audit entry per
claim id, each with `status` (supported/unsupported/disputed) and a one-sentence
`rationale`.
