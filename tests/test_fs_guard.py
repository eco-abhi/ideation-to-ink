import pytest

from engine.tools import fs_guard


@pytest.fixture(autouse=True)
def _papers_root(tmp_path, monkeypatch):
    monkeypatch.setattr(fs_guard, "PAPERS_ROOT", tmp_path)
    (tmp_path / "demo").mkdir()
    return tmp_path


def test_safe_write_writes_under_paper_dir(tmp_path):
    path = fs_guard.safe_write("demo", "ideation/notes.md", "hello", caller_agent="literature_scout")
    assert path == tmp_path / "demo" / "ideation" / "notes.md"
    assert path.read_text() == "hello"


def test_refs_bib_only_writable_by_citation_verifier():
    with pytest.raises(fs_guard.ArtifactWriteError):
        fs_guard.safe_write(
            "demo", "manuscript/refs.bib", "@article{x,}", caller_agent="section_drafters"
        )
    # the allowlisted agent succeeds
    fs_guard.safe_write("demo", "manuscript/refs.bib", "@article{x,}", caller_agent="citation_verifier")


def test_path_traversal_outside_paper_dir_rejected():
    with pytest.raises(fs_guard.ArtifactWriteError):
        fs_guard.safe_write("demo", "../../etc/passwd", "pwned", caller_agent="literature_scout")


def test_shell_escape_in_latex_rejected():
    with pytest.raises(fs_guard.UnsafeLatexError):
        fs_guard.safe_write(
            "demo",
            "manuscript/sections/intro.tex",
            r"\immediate\write18{rm -rf /}",
            caller_agent="section_drafters",
        )


def test_latex_escape_handles_special_chars():
    assert fs_guard.latex_escape("50% growth & $1M") == r"50\% growth \& \$1M"
