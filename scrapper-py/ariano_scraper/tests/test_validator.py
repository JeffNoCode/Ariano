from pathlib import Path

import pytest

from pdf.validator import validate_file_on_disk, validate_pdf_content
from schemas.document_schema import ExtractionMethod
from utils.errors import PdfValidationError

FIXTURES = Path(__file__).parent / "fixtures"


def test_valid_pdf_passes_file_validation():
    validate_file_on_disk(FIXTURES / "sample_edital.pdf") 


def test_valid_pdf_has_native_text():
    result = validate_pdf_content(FIXTURES / "sample_edital.pdf")
    assert result.extraction_method == ExtractionMethod.NATIVE_TEXT
    assert result.page_count == 3


def test_scanned_pdf_is_flagged_as_ocr_required():
    result = validate_pdf_content(FIXTURES / "scanned_like.pdf")
    assert result.extraction_method == ExtractionMethod.OCR_REQUIRED
    assert result.empty_page_ratio == 1.0


def test_missing_file_raises_validation_error():
    with pytest.raises(PdfValidationError):
        validate_file_on_disk(FIXTURES / "does_not_exist.pdf")


def test_invalid_signature_raises_validation_error():
    with pytest.raises(PdfValidationError):
        validate_file_on_disk(FIXTURES / "invalid_not_pdf.txt")


def test_corrupted_pdf_raises_validation_error():
    
    validate_file_on_disk(FIXTURES / "corrupted.pdf")
    with pytest.raises(PdfValidationError):
        validate_pdf_content(FIXTURES / "corrupted.pdf")


def test_empty_file_raises_validation_error(tmp_path):
    empty_file = tmp_path / "empty.pdf"
    empty_file.write_bytes(b"")
    with pytest.raises(PdfValidationError):
        validate_file_on_disk(empty_file)
