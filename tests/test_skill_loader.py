from engine.prompts.loader import (
    SKILLS_ROOT,
    build_system_prompt,
    load_skill,
    skill_ref,
    upstream_commit,
)


def test_upstream_commit_is_a_git_sha():
    commit = upstream_commit()
    assert len(commit) == 40
    assert all(c in "0123456789abcdef" for c in commit)


def test_load_skill_strips_frontmatter():
    body = load_skill("citation-verification-gate")
    assert not body.startswith("---")
    assert "name: citation-verification-gate" not in body
    assert "Citation Verification Gate" in body


def test_load_skill_missing_raises():
    import pytest

    with pytest.raises(FileNotFoundError):
        load_skill("does-not-exist")


def test_skill_ref_carries_upstream_commit():
    ref = skill_ref("literature-search")
    assert ref.name == "literature-search"
    assert ref.upstream_commit == upstream_commit()


def test_all_referenced_skills_exist():
    referenced = [
        "literature-search",
        "literature-review",
        "research-planning",
        "venue-submission-strategy",
        "reporting-guidelines-check",
        "experiment-report-bridge",
        "experiment-section-audit",
        "table-generation",
        "academic-plotting",
        "ml-paper-writing",
        "paper-schematics",
        "paper-writing-section",
        "related-work-writing",
        "latex-formatting",
        "latex-writeup-loop",
        "citation-verification-gate",
        "citation-management",
        "review-ensemble",
        "self-review",
        "claim-evidence-map",
        "claim-rigor-audit",
        "reverse-outline-flow-check",
        "long-form-manuscript-polish",
        "submission-qa-gate",
        "manuscript-scorecard",
        "paper-revision",
        "paper-redline-diff",
        "rebuttal-writing",
        "source-material-ingestion",
        "paper-memory-ledger",
        "paper-session-compaction",
    ]
    for name in referenced:
        assert (SKILLS_ROOT / name / "SKILL.md").exists(), name


def test_build_system_prompt_concatenates_skills():
    prompt = build_system_prompt(skills=["literature-search", "literature-review"])
    assert "literature-search" not in prompt.splitlines()[0]  # frontmatter gone
    assert len(prompt) > 0
