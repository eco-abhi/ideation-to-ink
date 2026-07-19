import bibtexparser

from engine.agents import section_drafters
from engine.llm import LLMResult
from engine.state import PaperState


def _fake_call_llm_json_factory():
    calls = []

    def _fake(messages, *, agent_name, schema, **kwargs):
        section = messages[-1]["content"].split("Draft the ")[-1].split(" section")[0]
        calls.append(section)
        drafted = schema(
            latex=f"This is the {section} section \\cite{{smith2023x}}.",
            citations=[{"key": "smith2023x", "title": "Smith et al Paper", "authors": ["A. Smith"], "year": 2023}],
            claims=[f"{section} claim one."],
        )
        return drafted, LLMResult(content="{}", model="fake/model", prompt_tokens=15, completion_tokens=25)

    return _fake, calls


def test_section_drafters_writes_sections_and_draft_bib(tmp_path, monkeypatch):
    fake_fn, calls = _fake_call_llm_json_factory()
    monkeypatch.setattr(section_drafters, "call_llm_json", fake_fn)
    monkeypatch.setattr(section_drafters.fs_guard, "PAPERS_ROOT", tmp_path)
    (tmp_path / "demo").mkdir()

    state = PaperState(
        paper_id="demo",
        topic="x",
        outline={"sections": ["abstract", "introduction"], "section_plans": {}},
    )
    result = section_drafters.section_drafters(state)

    assert calls == ["abstract", "introduction"]
    assert len(result.update["claims"]) == 2

    abstract_path = tmp_path / "demo" / "manuscript" / "sections" / "abstract.tex"
    assert abstract_path.exists()
    assert "\\cite{smith2023x}" in abstract_path.read_text()

    bib_path = tmp_path / "demo" / "manuscript" / "refs_draft.bib"
    assert bib_path.exists()
    db = bibtexparser.loads(bib_path.read_text())
    assert len(db.entries) == 1  # deduped: same citation proposed in both sections
    assert db.entries[0]["ID"] == "smith2023x"


def test_section_drafters_falls_back_to_default_sections(tmp_path, monkeypatch):
    fake_fn, calls = _fake_call_llm_json_factory()
    monkeypatch.setattr(section_drafters, "call_llm_json", fake_fn)
    monkeypatch.setattr(section_drafters.fs_guard, "PAPERS_ROOT", tmp_path)
    (tmp_path / "demo").mkdir()

    state = PaperState(paper_id="demo", topic="x", outline=None)
    section_drafters.section_drafters(state)

    assert calls == section_drafters.DEFAULT_SECTIONS
