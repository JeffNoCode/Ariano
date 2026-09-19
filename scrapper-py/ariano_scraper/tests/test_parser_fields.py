from datetime import date
from pathlib import Path

from pdf.extractor import extract_text_by_page, get_metadata_title
from pdf.normalizer import normalize_document
from parser.document_parser import parse_document
from schemas.document_schema import Confidence

FIXTURES = Path(__file__).parent / "fixtures"


def _parsed_sample():
    raw = extract_text_by_page(FIXTURES / "sample_edital.pdf")
    normalized = normalize_document(raw)
    title_metadata = get_metadata_title(FIXTURES / "sample_edital.pdf")
    return parse_document(normalized, pdf_title_metadata=title_metadata)


def test_title_comes_from_pdf_metadata_with_high_confidence():
    document_info, *_ = _parsed_sample()
    assert document_info.title is not None
    assert document_info.title.value == "Edital de Fomento à Inovação 2026"
    assert document_info.title.confidence == Confidence.HIGH
    assert document_info.title.source_page == 1


def test_organization_is_found():
    document_info, *_ = _parsed_sample()
    assert document_info.organization is not None
    assert "Secretaria" in document_info.organization.value
    assert document_info.organization.confidence == Confidence.MEDIUM


def test_submission_deadline_is_found_with_high_confidence():
    document_info, *_ = _parsed_sample()
    assert document_info.submission_deadline is not None
    assert document_info.submission_deadline.value == date(2026, 10, 30)
    assert document_info.submission_deadline.confidence == Confidence.HIGH
    assert document_info.submission_deadline.source_page == 2


def test_publication_date_from_textual_date_is_found():
    document_info, *_ = _parsed_sample()
    assert document_info.publication_date is not None
    assert document_info.publication_date.value == date(2026, 12, 15)


def test_budget_is_found_with_high_confidence():
    _, _, _, financial, *_ = _parsed_sample()
    assert financial.budget is not None
    assert financial.budget.value == 1500000.00
    assert financial.budget.confidence == Confidence.HIGH
    assert financial.currency == "BRL"


def test_requirements_are_extracted_from_requirements_section():
    _, requirements, *_ = _parsed_sample()
    texts = [r.text for r in requirements]
    assert any("CNPJ" in t for t in texts)
    assert len(requirements) == 6
    for r in requirements:
        assert r.confidence == Confidence.MEDIUM
        assert r.source_page == 2


def test_known_competencies_are_recognized():
    _, _, competencies, *_ = _parsed_sample()
    codes = {c.code for c in competencies}
    assert "AI" in codes
    assert "PYTHON" in codes
    assert "WHATSAPP" in codes
    assert "AUTOMATION" in codes
    assert "ML" in codes


def test_competency_carries_source_page_and_matched_text():
    _, _, competencies, *_ = _parsed_sample()
    ai_competency = next(c for c in competencies if c.code == "AI")
    assert ai_competency.source_page == 1
    assert ai_competency.matched_text != ""
    assert ai_competency.confidence in (Confidence.HIGH, Confidence.MEDIUM)


def test_unrelated_competency_is_not_found():
    _, _, competencies, *_ = _parsed_sample()
    codes = {c.code for c in competencies}
    assert "BLOCKCHAIN" not in codes  


def test_no_warnings_for_a_well_formed_document():
    *_, warnings = _parsed_sample()
    assert warnings == []
