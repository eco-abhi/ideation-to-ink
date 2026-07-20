import shutil
import subprocess

import pytest

from engine.graphs import writing
from engine.state import PaperState


def _setup(tmp_path, monkeypatch, *, venue=None):
    monkeypatch.setattr(writing, "paper_dir", lambda slug: tmp_path / slug)
    monkeypatch.setattr(writing.fs_guard, "PAPERS_ROOT", tmp_path)
    pdir = tmp_path / "demo"
    sections_dir = pdir / "manuscript" / "sections"
    sections_dir.mkdir(parents=True)
    (sections_dir / "introduction.tex").write_text("Intro text.")
    (sections_dir / "methods.tex").write_text("Methods text.")
    (sections_dir / "extra_not_in_outline.tex").write_text("Extra text.")
    return pdir


def test_assemble_main_tex_orders_sections_and_appends_extras(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(writing, "get_venue", lambda slug: None)

    state = PaperState(
        paper_id="demo",
        topic="Exception Handling with LLM Agents",
        outline={"sections": ["methods", "introduction"]},
    )
    relpath = writing._assemble_main_tex(state)
    assert relpath == "manuscript/main.tex"

    main_tex = (tmp_path / "demo" / "manuscript" / "main.tex").read_text()
    methods_pos = main_tex.index("\\input{sections/methods}")
    intro_pos = main_tex.index("\\input{sections/introduction}")
    extra_pos = main_tex.index("\\input{sections/extra_not_in_outline}")
    assert methods_pos < intro_pos < extra_pos  # outline order first, then extras
    assert "\\documentclass" in main_tex
    assert "\\begin{document}" in main_tex
    assert "\\end{document}" in main_tex
    assert "Exception Handling with LLM Agents" in main_tex


def test_assemble_main_tex_uses_venue_template(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        writing,
        "get_venue",
        lambda slug: {"latex_template": "shared/templates/neurips-style.tex"},
    )

    state = PaperState(paper_id="demo", topic="x", venue="neurips-style", outline={"sections": ["introduction"]})
    writing._assemble_main_tex(state)

    main_tex = (tmp_path / "demo" / "manuscript" / "main.tex").read_text()
    assert "neurips_2024" in main_tex  # only the real venue template includes this package
    assert "\\bibliographystyle{unsrtnat}" in main_tex


def test_assembled_main_tex_escapes_special_chars_in_title(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(writing, "get_venue", lambda slug: None)

    state = PaperState(paper_id="demo", topic="Cost & Risk: A 10% Improvement", outline={"sections": []})
    writing._assemble_main_tex(state)

    main_tex = (tmp_path / "demo" / "manuscript" / "main.tex").read_text()
    assert "Cost \\& Risk" in main_tex
    assert "10\\%" in main_tex


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed in this environment")
def test_assembled_main_tex_actually_compiles(tmp_path, monkeypatch):
    pdir = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(writing, "get_venue", lambda slug: None)

    (pdir / "manuscript" / "refs.bib").write_text("")
    state = PaperState(paper_id="demo", topic="A Compilable Paper", outline={"sections": ["introduction", "methods"]})
    writing._assemble_main_tex(state)

    result = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
        cwd=pdir / "manuscript",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout[-2000:]
