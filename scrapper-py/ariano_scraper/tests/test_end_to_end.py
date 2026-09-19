import json
from pathlib import Path

from main import process_pdf
from utils.logging import setup_logging

FIXTURES = Path(__file__).parent / "fixtures"


def test_full_pipeline_produces_valid_json_on_disk(tmp_path):
    logger = setup_logging()
    pdf_path = FIXTURES / "sample_edital.pdf"

    output_path, final_document = process_pdf(
        pdf_path=pdf_path,
        output_dir=tmp_path,
        known_tags_path=None,
        logger=logger,
    )

    assert output_path.exists()
    assert output_path.suffix == ".json"

    with open(output_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    assert payload["processing_metadata"]["document_hash"].startswith("sha256:")
    assert payload["processing_metadata"]["parser_version"] == "1.0.0"
    assert payload["processing_metadata"]["extraction_method"] == "native_text"
    assert payload["processing_metadata"]["page_count"] == 3

    assert payload["document"]["title"]["value"] == "Edital de Fomento à Inovação 2026"
    assert payload["document"]["submission_deadline"]["value"] == "2026-10-30"

    assert len(payload["competencies"]) >= 5
    assert len(payload["requirements"]) == 6
    assert len(payload["sections"]) >= 6

    raw_text = output_path.read_text(encoding="utf-8")
    assert "Inovação" in raw_text
    assert "\\u" not in raw_text

    assert final_document.processing_metadata.page_count == 3
    assert final_document.document.title.value == payload["document"]["title"]["value"]


def test_pipeline_on_scanned_pdf_does_not_crash_and_flags_ocr(tmp_path):
    logger = setup_logging()
    pdf_path = FIXTURES / "scanned_like.pdf"

    output_path, final_document = process_pdf(
        pdf_path=pdf_path,
        output_dir=tmp_path,
        known_tags_path=None,
        logger=logger,
    )

    assert output_path.exists()
    assert final_document.processing_metadata.extraction_method.value == "ocr_required"
    assert any("OCR" in w for w in final_document.extraction_warnings)
    
    assert final_document.document.submission_deadline is None
    assert final_document.competencies == []


def test_pipeline_raises_pipeline_error_for_corrupted_pdf(tmp_path):
    from utils.errors import PipelineError

    logger = setup_logging()
    try:
        process_pdf(
            pdf_path=FIXTURES / "corrupted.pdf",
            output_dir=tmp_path,
            known_tags_path=None,
            logger=logger,
        )
        assert False, "Deveria ter levantado PipelineError"
    except PipelineError as exc:
        assert exc.stage == "PDF_VALIDATION"
