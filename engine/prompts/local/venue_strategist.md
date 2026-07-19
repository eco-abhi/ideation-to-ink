## Project-Specific Task: Venue Ranking

Rank every configured venue below against this paper's topic, research questions,
and deadline. Use the venue's `scope_keywords`, `family`, `page_limit_main`, and
`typical_deadline_month` -- do not invent venues that aren't in this list.

Topic: {topic}

Research questions:
{research_questions}

Deadline: {deadline}

Configured venues:
{venues}

For each venue, give a rank (1 = best fit) and a one-sentence rationale grounded
in the venue's actual scope/constraints above, not generic praise. Then pick the
single best `chosen_slug` and justify it in `chosen_rationale`, specifically
addressing why it beats the runner-up.

Respond with only the JSON object the schema requires.
