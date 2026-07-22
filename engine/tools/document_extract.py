"""Extracts plain text from an uploaded PDF/DOCX for the dashboard's "import
existing paper" file-upload path. Legacy binary .doc is deliberately
unsupported -- reliable extraction needs external tools (LibreOffice/antiword),
not a pure-Python library, and isn't worth the fragility here.
"""

from __future__ import annotations

import io

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


class UnsupportedDocumentError(ValueError):
    pass


def _suffix(filename: str) -> str:
    return f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""


def _extract_pdf(content: bytes) -> str:
    import pdfplumber

    pages = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)
    return "\n\n".join(pages)


def _extract_docx(content: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(content))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def extract_text(filename: str, content: bytes) -> str:
    suffix = _suffix(filename)

    if suffix == ".pdf":
        text = _extract_pdf(content)
    elif suffix == ".docx":
        text = _extract_docx(content)
    elif suffix == ".doc":
        raise UnsupportedDocumentError(
            "Legacy .doc files aren't supported -- reliable extraction needs external tools "
            "(LibreOffice/antiword) this pipeline doesn't depend on. Save as .docx or PDF and try again."
        )
    else:
        raise UnsupportedDocumentError(
            f"Unsupported file type {suffix or '(no extension)'!r}. Supported: {sorted(SUPPORTED_EXTENSIONS)}."
        )

    if not text.strip():
        raise UnsupportedDocumentError(
            f"No extractable text found in {filename!r} -- if this is a PDF, it may be scanned/image-based "
            "(OCR isn't supported here); try pasting the text manually instead."
        )
    return text
