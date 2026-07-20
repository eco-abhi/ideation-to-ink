import bibtexparser
from graph_helpers import compiled_graph
from langgraph.types import Command

from engine.agents.base import NodeResult
from engine.graphs import writing
from engine.state import CitationRecord


def _fake_structure_agent(state):
    return NodeResult(update={"outline": {"sections": ["intro"], "section_plans": {}}})


def _fake_section_drafters(state):
    return NodeResult(update={})


def _make_fake_citation_verifier(records: list[CitationRecord], bib_keys: list[str]):
    def _fake(state):
        return NodeResult(update={"citation_records": records, "bib_keys": bib_keys})

    return _fake


def test_no_suspicious_citations_skips_interrupt(tmp_path, monkeypatch):
    monkeypatch.setattr(writing, "structure_agent", _fake_structure_agent)
    monkeypatch.setattr(writing, "section_drafters", _fake_section_drafters)
    monkeypatch.setattr(
        writing,
        "citation_verifier",
        _make_fake_citation_verifier(
            [CitationRecord(bib_key="a1", status="verified", rationale="ok")], ["a1"]
        ),
    )
    monkeypatch.setattr(writing, "paper_dir", lambda slug: tmp_path / slug)
    monkeypatch.setattr(writing.fs_guard, "PAPERS_ROOT", tmp_path)
    (tmp_path / "demo").mkdir()

    with compiled_graph(writing.add_writing_nodes, entry_node=writing.ENTRY_NODE, exit_node=writing.WRITING_COMPLETE) as graph:
        config = {"configurable": {"thread_id": "demo"}}
        final = graph.invoke({"paper_id": "demo", "topic": "x", "phase": "writing"}, config)
        assert "__interrupt__" not in final
        assert final["bib_keys"] == ["a1"]
        assert final["artifacts"]["main_tex"] == "manuscript/main.tex"


def test_suspicious_citations_pause_and_human_approval_merges_into_refs_bib(tmp_path, monkeypatch):
    monkeypatch.setattr(writing, "structure_agent", _fake_structure_agent)
    monkeypatch.setattr(writing, "section_drafters", _fake_section_drafters)
    suspicious_record = CitationRecord(bib_key="susp2023", status="suspicious", rationale="weak match")
    monkeypatch.setattr(
        writing,
        "citation_verifier",
        _make_fake_citation_verifier([suspicious_record], []),
    )
    monkeypatch.setattr(writing, "paper_dir", lambda slug: tmp_path / slug)
    monkeypatch.setattr(writing.fs_guard, "PAPERS_ROOT", tmp_path)

    pdir = tmp_path / "demo"
    (pdir / "manuscript").mkdir(parents=True)
    (pdir / "manuscript" / "refs_draft.bib").write_text(
        "@article{susp2023,\n  title = {A Suspicious Paper},\n  author = {X},\n  year = {2023}\n}\n"
    )
    (pdir / "manuscript" / "refs.bib").write_text("")

    with compiled_graph(writing.add_writing_nodes, entry_node=writing.ENTRY_NODE, exit_node=writing.WRITING_COMPLETE) as graph:
        config = {"configurable": {"thread_id": "demo"}}
        result = graph.invoke({"paper_id": "demo", "topic": "x", "phase": "writing"}, config)
        assert "__interrupt__" in result
        assert result["__interrupt__"][0].value["type"] == "suspicious_citations"

        final = graph.invoke(Command(resume={"approve": ["susp2023"]}), config)
        assert final["bib_keys"] == ["susp2023"]

    final_bib = (pdir / "manuscript" / "refs.bib").read_text()
    db = bibtexparser.loads(final_bib)
    assert {e["ID"] for e in db.entries} == {"susp2023"}


def test_node_failure_routes_to_error_gate(monkeypatch):
    def _fails(state):
        raise RuntimeError("llm down")

    monkeypatch.setattr(writing, "structure_agent", _fails)

    with compiled_graph(writing.add_writing_nodes, entry_node=writing.ENTRY_NODE, exit_node=writing.WRITING_COMPLETE) as graph:
        config = {"configurable": {"thread_id": "demo"}}
        result = graph.invoke({"paper_id": "demo", "topic": "x", "phase": "writing"}, config)
        assert "__interrupt__" in result
        assert "llm down" in result["errors"][0]
