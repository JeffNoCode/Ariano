import hashlib
import json
from io import BytesIO
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, UploadFile

from ariano_api import main


def test_ingest_reuses_pdf_by_hash_without_running_parser(monkeypatch):
    content = b"%PDF-1.7 fixture"
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    conn = Mock()
    lookup = Mock(return_value={
        "id": 12, "document_hash": digest, "title": "Edital",
        "payload": {"competencies": [{"code": "NLP"}], "extraction_warnings": ["aviso"]},
    })
    parser = Mock()
    monkeypatch.setattr(main.repo, "find_document_for_ingest", lookup)
    monkeypatch.setattr(main.document_service, "run_scraper", parser)

    result = main.ingest_document(UploadFile(BytesIO(content)), {"id": 1}, conn)

    lookup.assert_called_once_with(conn, digest)
    parser.assert_not_called()
    conn.commit.assert_not_called()
    assert result == {
        "id": 12, "document_hash": digest, "title": "Edital", "already_existed": True,
        "competencies": [{"code": "NLP"}], "extraction_warnings": ["aviso"],
    }


def test_ingest_reports_subprocess_timeout(monkeypatch):
    monkeypatch.setattr(main.repo, "find_document_for_ingest", Mock(return_value=None))
    parser = Mock(side_effect=TimeoutExpired(["parser"], timeout=10))
    monkeypatch.setattr(main.document_service, "run_scraper", parser)

    with pytest.raises(HTTPException, match="tempo limite") as error:
        main.ingest_document(UploadFile(BytesIO(b"%PDF-1.7 fixture")), {"id": 1}, Mock())

    assert error.value.status_code == 504

@pytest.mark.parametrize(("filename", "expected"), [(r"C:\documentos\edital.pdf", "edital.pdf"), ("..", "upload.pdf")])
def test_scraper_isolates_temp_filename(monkeypatch, tmp_path, filename, expected):
    service = main.document_service
    monkeypatch.setattr(service, "SCRAPER_DIR", tmp_path)

    def fake_parser(args, **kwargs):
        input_path = Path(args[2])
        assert input_path.name == "upload.pdf"
        assert input_path.read_bytes() == b"%PDF-1.7 fixture"
        output = Path(args[-1]) / "upload.json"
        output.write_text(json.dumps({"processing_metadata": {"source_file": str(input_path)}}))
        return CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(service.subprocess, "run", fake_parser)
    result = service.run_scraper(b"%PDF-1.7 fixture", filename)

    assert result["processing_metadata"]["source_file"] == expected
