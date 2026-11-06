"""Capability 1: read text from typed documents (TXT, MD, CSV, JSON, DOCX, PDF)."""

import io
import re
import zipfile
from pathlib import Path

PLAIN = {".txt", ".md", ".csv", ".json", ".log"}
SUPPORTED = PLAIN | {".docx", ".pdf"}


def read_text(name, data):
    """Return {"text", "method", "error"} for one uploaded document."""
    suffix = Path(name).suffix.lower()
    if suffix in PLAIN:
        return {"text": data.decode("utf-8", errors="replace"), "method": "plain text", "error": None}
    if suffix == ".docx":
        return _docx(data)
    if suffix == ".pdf":
        return _pdf(data)
    return {"text": "", "method": None, "error": f"{suffix or 'this file'} is not a text document"}


def _docx(data):
    # A .docx is a zip with the body in word/document.xml; no extra library needed.
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError) as error:
        return {"text": "", "method": "docx", "error": f"Not a readable Word file: {error}"}
    xml = re.sub(r"</w:p>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    return {"text": _unescape(text).strip(), "method": "docx", "error": None}


def _pdf(data):
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"text": "", "method": "pdf", "error": "PDF reading needs `pypdf` (pip install pypdf)."}
    try:
        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    except Exception as error:  # pypdf raises many types on damaged files
        return {"text": "", "method": "pdf", "error": f"Could not read PDF: {error}"}
    if not text.strip():
        return {"text": "", "method": "pdf", "error": "PDF has no text layer (scanned): use image_text on the pages."}
    return {"text": text.strip(), "method": "pdf", "error": None}


def _unescape(text):
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        text = text.replace(entity, char)
    return text
