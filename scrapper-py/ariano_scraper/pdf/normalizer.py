from __future__ import annotations

import re
import unicodedata

from pdf.extractor import ExtractedDocument, PageText

_CONTROL_CHARS_RE = re.compile(
    "[" + "".join(chr(c) for c in range(0, 32) if chr(c) not in "\n\t") + "]"
)

_MULTIPLE_SPACES_RE = re.compile(r"[ \t]{2,}")
_MULTIPLE_BLANK_LINES_RE = re.compile(r"\n{3,}")

_HYPHENATION_RE = re.compile(r"([^\W\d_])-\n([a-zà-ÿ]+)")


def _fix_hyphenation(text: str) -> str:
    return _HYPHENATION_RE.sub(r"\1\2", text)


def normalize_text(text: str) -> str:

    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    text = _CONTROL_CHARS_RE.sub("", text)
    
    text = _fix_hyphenation(text)

    text = _MULTIPLE_SPACES_RE.sub(" ", text)

    text = _MULTIPLE_BLANK_LINES_RE.sub("\n\n", text)

    lines = [line.strip(" \t") for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()


def normalize_document(document: ExtractedDocument) -> ExtractedDocument:

    normalized_pages = [
        PageText(page=p.page, text=normalize_text(p.text)) for p in document.pages
    ]
    return ExtractedDocument(pages=normalized_pages)
