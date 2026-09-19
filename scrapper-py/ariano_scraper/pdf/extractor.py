from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pdfplumber

from utils.errors import PdfExtractionError


@dataclass
class PageText:
    page: int
    text: str


@dataclass
class ExtractedDocument:
    pages: List[PageText] = field(default_factory=list)

    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)

    def text_of_page(self, page_number: int) -> str:
        for p in self.pages:
            if p.page == page_number:
                return p.text
        return ""


def extract_text_by_page(path: Path) -> ExtractedDocument:

    try:
        pdf = pdfplumber.open(str(path))
    except Exception as exc:
        raise PdfExtractionError(f"Failed to open PDF for extraction: {exc}") from exc

    pages: List[PageText] = []
    try:
        for index, page in enumerate(pdf.pages, start=1):
            try:
                raw_text = page.extract_text() or ""
            except Exception:
                
                raw_text = ""
            pages.append(PageText(page=index, text=raw_text))
    finally:
        pdf.close()

    if not pages:
        raise PdfExtractionError("No pages were extracted from the PDF.")

    return ExtractedDocument(pages=pages)


def get_metadata_title(path: Path) -> Optional[str]:
    try:
        pdf = pdfplumber.open(str(path))
    except Exception:
        return None

    try:
        metadata = pdf.metadata or {}
        title = metadata.get("Title")
        return title.strip() if title else None
    finally:
        pdf.close()
