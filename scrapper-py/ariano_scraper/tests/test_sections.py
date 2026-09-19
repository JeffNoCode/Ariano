from pathlib import Path

from pdf.extractor import extract_text_by_page
from pdf.normalizer import normalize_document
from parser.document_parser import detect_sections, is_heading_line

FIXTURES = Path(__file__).parent / "fixtures"


def test_recognizes_plain_heading():
    assert is_heading_line("OBJETIVO") == "OBJETIVO"


def test_recognizes_heading_with_numbering_dot():
    assert is_heading_line("1. OBJETIVO") == "OBJETIVO"


def test_recognizes_heading_with_numbering_dash():
    assert is_heading_line("1 - OBJETIVO") == "OBJETIVO"


def test_recognizes_heading_with_article_prefix():
    assert is_heading_line("1. DO OBJETIVO") == "OBJETIVO"
    assert is_heading_line("DO OBJETO") == "OBJETIVO"


def test_recognizes_heading_with_mixed_case():
    assert is_heading_line("Objetivo") == "OBJETIVO"


def test_recognizes_heading_with_accent_variation():
    assert is_heading_line("PÚBLICO-ALVO") == "PÚBLICO-ALVO"
    assert is_heading_line("PUBLICO-ALVO") == "PÚBLICO-ALVO"
    assert is_heading_line("CRITÉRIOS DE ELEGIBILIDADE") == "CRITÉRIOS DE ELEGIBILIDADE"


def test_does_not_match_heading_keyword_inside_a_sentence():

    assert is_heading_line("O objetivo deste edital é apoiar startups.") is None


def test_does_not_match_unrelated_line():
    assert is_heading_line("Este é apenas um parágrafo qualquer do documento.") is None


def test_detect_sections_on_sample_fixture():
    raw = extract_text_by_page(FIXTURES / "sample_edital.pdf")
    normalized = normalize_document(raw)

    sections = detect_sections(normalized)
    headings = [s.heading for s in sections]

    assert "OBJETIVO" in headings
    assert "PÚBLICO-ALVO" in headings
    assert "REQUISITOS" in headings
    assert "CRITÉRIOS DE ELEGIBILIDADE" in headings
    assert "PRAZOS" in headings
    assert "VALOR" in headings

    objetivo_section = next(s for s in sections if s.heading == "OBJETIVO")
    assert objetivo_section.page == 1
    assert "Automacao" in objetivo_section.text or "Automação" in objetivo_section.text
