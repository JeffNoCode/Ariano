from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from schemas.document_schema import (
    Competency,
    Confidence,
    DocumentInfo,
    ExtractionMethod,
    Financial,
    FinalDocument,
    ProcessingMetadata,
    Requirement,
    Section,
    TrackedValue,
)


def _valid_metadata() -> ProcessingMetadata:
    return ProcessingMetadata(
        source_url=None,
        source_file="documents/example.pdf",
        document_hash="sha256:abc123",
        processed_at=datetime.now(timezone.utc),
        parser_version="1.0.0",
        extraction_method=ExtractionMethod.NATIVE_TEXT,
        ocr_used=False,
        page_count=3,
    )


def test_valid_final_document_is_accepted():
    doc = FinalDocument(
        processing_metadata=_valid_metadata(),
        document=DocumentInfo(
            title=TrackedValue(value="Edital de Exemplo", confidence=Confidence.HIGH, source_page=1),
            submission_deadline=TrackedValue(value=date(2026, 10, 30), confidence=Confidence.HIGH, source_page=2),
        ),
        requirements=[Requirement(text="Possuir CNPJ ativo", confidence=Confidence.MEDIUM, source_page=2)],
        competencies=[
            Competency(code="AI", name="Artificial Intelligence", confidence=Confidence.HIGH, source_page=1, matched_text="IA")
        ],
        financial=Financial(budget=TrackedValue(value=1500000.0, confidence=Confidence.HIGH, source_page=3)),
        sections=[Section(heading="OBJETIVO", page=1, text="Texto da seção.")],
        extraction_warnings=[],
    )
    assert doc.document.title.value == "Edital de Exemplo"
    assert doc.processing_metadata.page_count == 3


def test_invalid_confidence_value_is_rejected():
    with pytest.raises(ValidationError):
        TrackedValue(value="x", confidence="SUPER_HIGH", source_page=1)  


def test_source_page_must_be_at_least_one():
    with pytest.raises(ValidationError):
        TrackedValue(value="x", confidence=Confidence.HIGH, source_page=0)


def test_missing_required_field_is_rejected():
    with pytest.raises(ValidationError):
  
        ProcessingMetadata(
            document_hash="sha256:abc",
            processed_at=datetime.now(timezone.utc),
            parser_version="1.0.0",
            extraction_method=ExtractionMethod.NATIVE_TEXT,
            page_count=1,
        )


def test_invalid_extraction_method_is_rejected():
    with pytest.raises(ValidationError):
        ProcessingMetadata(
            source_file="a.pdf",
            document_hash="sha256:abc",
            processed_at=datetime.now(timezone.utc),
            parser_version="1.0.0",
            extraction_method="not_a_real_method",
            page_count=1,
        )


def test_negative_page_count_is_rejected():
    with pytest.raises(ValidationError):
        ProcessingMetadata(
            source_file="a.pdf",
            document_hash="sha256:abc",
            processed_at=datetime.now(timezone.utc),
            parser_version="1.0.0",
            extraction_method=ExtractionMethod.NATIVE_TEXT,
            page_count=-1,
        )


def test_extra_unexpected_field_is_rejected():
    # model_config = extra="forbid" em TrackedValue: um campo desconhecido deve falhar,
    # não ser silenciosamente ignorado.
    with pytest.raises(ValidationError):
        TrackedValue(value="x", confidence=Confidence.HIGH, source_page=1, campo_inventado="qualquer coisa")


def test_final_document_defaults_are_empty_collections():
    doc = FinalDocument(processing_metadata=_valid_metadata(), document=DocumentInfo())
    assert doc.requirements == []
    assert doc.competencies == []
    assert doc.sections == []
    assert doc.extraction_warnings == []
    assert doc.financial.budget is None
    assert doc.financial.currency == "BRL"
