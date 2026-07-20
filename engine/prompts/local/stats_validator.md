## Project-Specific Task: Results Validation + Manuscript Handoff

You have the experiment design and the raw results/metrics.json this run
produced. Two jobs:

1. **Audit**: does this results file support rigorous claims? Check
   specifically for significance tests, effect sizes (not just point
   estimates), and whether every number could plausibly be traced back to a
   raw output rather than being invented. List concrete issues, not generic
   advice.
2. **Bridge**: write a paper-ready Markdown results summary
   (`results_summary_md`) that `section_drafters` can draw numbers from
   directly -- reference the exact metric names and values from
   metrics.json, do not round or reword numbers, and write an explicit TODO
   for anything the design called for that the results file doesn't actually
   contain rather than filling the gap with a plausible-sounding number.

Experiment design:
{design}

Raw results (metrics.json):
{metrics_json}

Respond with only the JSON object the schema requires.
