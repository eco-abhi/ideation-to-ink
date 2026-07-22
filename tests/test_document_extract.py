import io

import docx
import pytest

from engine.tools import document_extract


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def test_extract_docx_reads_real_paragraphs():
    content = _make_docx_bytes(["Title of the Paper", "", "First paragraph of the abstract.", "Second paragraph."])
    text = document_extract.extract_text("paper.docx", content)
    assert "Title of the Paper" in text
    assert "First paragraph of the abstract." in text
    assert "Second paragraph." in text


def test_extract_docx_skips_empty_paragraphs():
    content = _make_docx_bytes(["Real content.", "   ", "", "More content."])
    text = document_extract.extract_text("paper.docx", content)
    # empty/whitespace-only paragraphs shouldn't produce blank noise between real content
    assert "Real content.\n\nMore content." in text


def test_extract_text_rejects_legacy_doc():
    with pytest.raises(document_extract.UnsupportedDocumentError, match="Legacy .doc"):
        document_extract.extract_text("paper.doc", b"whatever")


def test_extract_text_rejects_unknown_extension():
    with pytest.raises(document_extract.UnsupportedDocumentError, match="Unsupported file type"):
        document_extract.extract_text("paper.txt", b"whatever")


def test_extract_text_rejects_no_extension():
    with pytest.raises(document_extract.UnsupportedDocumentError, match="no extension"):
        document_extract.extract_text("paper", b"whatever")


def test_extract_pdf_dispatches_and_rejects_empty_result(monkeypatch):
    # A thin, obviously-correct wrapper around pdfplumber's own extract_text() --
    # tested at the dispatch/error-handling layer rather than via a hand-built
    # binary PDF fixture, which would test pdfplumber more than this module.
    monkeypatch.setattr(document_extract, "_extract_pdf", lambda content: "Real extracted PDF text.")
    text = document_extract.extract_text("paper.pdf", b"fake-pdf-bytes")
    assert text == "Real extracted PDF text."


def test_extract_pdf_scanned_with_no_text_layer_raises_clear_error(monkeypatch):
    monkeypatch.setattr(document_extract, "_extract_pdf", lambda content: "   ")
    with pytest.raises(document_extract.UnsupportedDocumentError, match="scanned/image-based"):
        document_extract.extract_text("scanned.pdf", b"fake-pdf-bytes")
