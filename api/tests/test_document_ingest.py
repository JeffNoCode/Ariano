import hashlib
from io import BytesIO
from subprocess import TimeoutExpired
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
