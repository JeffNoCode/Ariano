from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pdfplumber

from schemas.document_schema import ExtractionMethod
from utils.errors import PdfValidationError

_PDF_SIGNATURE = b"%PDF-"

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

_MIN_CHARS_PER_PAGE = 20

_EMPTY_PAGE_RATIO_FOR_OCR = 0.5


@dataclass
class ValidationResult:
    

    page_count: int
    extraction_method: ExtractionMethod
    empty_page_ratio: float


def validate_file_on_disk(path: Path) -> None:
 
    if not path.exists():
        raise PdfValidationError(f"File does not exist: {path}")

    if not path.is_file():
        raise PdfValidationError(f"Path is not a file: {path}")

    size = path.stat().st_size
    if size == 0:
        raise PdfValidationError(f"File is empty: {path}")

    if size > MAX_FILE_SIZE_BYTES:
        raise PdfValidationError(
            f"File exceeds maximum accepted size "
            f"({size} bytes > {MAX_FILE_SIZE_BYTES} bytes): {path}"
        )

    with open(path, "rb") as f:
        header = f.read(len(_PDF_SIGNATURE))
    if header != _PDF_SIGNATURE:
        raise PdfValidationError(
            f"Invalid PDF signature (expected '%PDF-', got {header!r}): {path}"
        )


def validate_pdf_content(path: Path) -> ValidationResult:
   
    try:
        pdf = pdfplumber.open(str(path))
    except Exception as exc:  
        raise PdfValidationError(f"Could not open PDF (possibly corrupted): {exc}") from exc

    try:
        page_count = len(pdf.pages)
        if page_count == 0:
            raise PdfValidationError(f"PDF has no pages: {path}")

        empty_pages = 0
        for page in pdf.pages:
            text: Optional[str] = page.extract_text()
            if text is None or len(text.strip()) < _MIN_CHARS_PER_PAGE:
                empty_pages += 1

        empty_page_ratio = empty_pages / page_count

        extraction_method = (
            ExtractionMethod.OCR_REQUIRED
            if empty_page_ratio > _EMPTY_PAGE_RATIO_FOR_OCR
            else ExtractionMethod.NATIVE_TEXT
        )

        return ValidationResult(
            page_count=page_count,
            extraction_method=extraction_method,
            empty_page_ratio=empty_page_ratio,
        )
    finally:
        pdf.close()
