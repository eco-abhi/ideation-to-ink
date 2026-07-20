## Project-Specific Task: Claim Extraction from an Imported Section

This LaTeX section was imported from an existing draft, not written by this
pipeline. Extract every load-bearing factual claim it makes as plain text (one
sentence each), independent of whether it currently has a `\cite{{}}` attached --
downstream `claims_evidence_auditor` needs the full list to audit, not just the
already-cited ones.

Section name: {section_name}

LaTeX:
{latex}

Respond with only the JSON object the schema requires.
