"""Exercise the currently implemented HTTP flow against a running ARIANO API."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

AUTH_TOKEN = None


def call(base: str, method: str, path: str, payload=None, *, expected: int = 200, content_type=None):
    data = None
    if payload is not None:
        if content_type is None:
            content_type = "application/json"
            data = json.dumps(payload).encode("utf-8")
        else:
            data = payload
    headers = {"Content-Type": content_type} if content_type else {}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    request = Request(base + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=130) as response:
            status = response.status
            body = response.read()
    except HTTPError as exc:
        status = exc.code
        body = exc.read()
    if status != expected:
        raise AssertionError(f"{method} {path}: HTTP {status}, esperado {expected}; {body[:800]!r}")
    return json.loads(body) if body else None


def upload_pdf(base: str, pdf_path: Path, *, expected: int = 201):
    boundary = "ariano-" + uuid4().hex
    content = pdf_path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{pdf_path.name}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return call(
        base,
        "POST",
        "/documents",
        body,
        expected=expected,
        content_type=f"multipart/form-data; boundary={boundary}",
    )


def main() -> None:
    global AUTH_TOKEN
    parser = argparse.ArgumentParser(description="Smoke test da API ARIANO")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "scrapper-py"
        / "ariano_scraper"
        / "tests"
        / "fixtures"
        / "sample_edital.pdf",
    )
    args = parser.parse_args()
    base = args.url.rstrip("/")
    if not args.pdf.is_file():
        parser.error(f"PDF de teste não encontrado: {args.pdf}")
    email = os.environ.get("ARIANO_TEST_ADMIN_EMAIL")
    password = os.environ.get("ARIANO_TEST_ADMIN_PASSWORD") or getpass.getpass("Senha do administrador: ")
    if not email or not password:
        parser.error("defina ARIANO_TEST_ADMIN_EMAIL e informe a senha")
    AUTH_TOKEN = call(base, "POST", "/auth/login", {"email": email, "password": password})["access_token"]

    health = call(base, "GET", "/health")
    assert health == {"status": "ok", "database": "ok", "engine": "ok"}
    openapi = call(base, "GET", "/openapi.json")
    assert "/documents" in openapi["paths"]

    suffix = uuid4().hex[:10].upper()
    source = call(base, "POST", "/tags", {"code": f"SMOKE_{suffix}_SOURCE", "name": "Fonte de teste"}, expected=201)
    target = call(base, "POST", "/tags", {"code": f"SMOKE_{suffix}_TARGET", "name": "Alvo de teste"}, expected=201)
    assert {source["id"], target["id"]}.issubset({row["id"] for row in call(base, "GET", "/tags")})
    relation = call(base, "PUT", "/tags/relationships", {
        "source_tag_id": source["id"], "target_tag_id": target["id"],
        "relation_type": "RELATED", "weight": 0.9,
    })
    assert relation["weight"] == 0.9

    actor = call(base, "POST", "/actors", {
        "type": "ORGANIZATION", "name": f"Teste integrado {suffix}",
        "profile": {"business_sector": "Teste"},
        "tags": [{"tag_id": source["id"], "weight": 1.0}],
    }, expected=201)
    actor_id = actor["id"]
    assert call(base, "GET", f"/actors/{actor_id}")["id"] == actor_id
    assert actor_id in {row["id"] for row in call(base, "GET", "/actors?limit=500")}

    document = upload_pdf(base, args.pdf)
    document_id = document["id"]
    assert document_id == call(base, "GET", f"/documents/{document_id}")["id"]
    duplicate = upload_pdf(base, args.pdf)
    assert duplicate["id"] == document_id and duplicate["already_existed"]

    demand = call(base, "POST", "/demands", {
        "requester_id": actor_id, "document_id": document_id,
        "title": f"Demanda de teste {suffix}",
        "tags": [{"tag_id": target["id"], "type": "REQUIRED", "weight": 1.0}],
    }, expected=201)
    demand_id = demand["id"]
    assert call(base, "GET", f"/demands/{demand_id}")["id"] == demand_id

    ranking = call(base, "POST", f"/demands/{demand_id}/match", {"persist": True})
    result = next(row for row in ranking["results"] if row["actor_id"] == actor_id)
    assert result["match_class"] == "RELATED" and abs(result["score"] - 0.9) < 1e-8
    stored = call(base, "GET", f"/demands/{demand_id}/matches")
    stored_result = next(row for row in stored if row["actor_id"] == actor_id)
    details = call(base, "GET", f"/matches/{stored_result['id']}/details")
    assert any(row["demand_tag_id"] == target["id"] for row in details)

    call(base, "POST", "/actors", {
        "type": "ORGANIZATION", "name": "Peso inválido",
        "tags": [{"tag_id": source["id"], "weight": 1.5}],
    }, expected=422)
    call(base, "GET", f"/actors/{actor_id + 1_000_000_000}", expected=404)
    call(base, "GET", f"/demands/{demand_id + 1_000_000_000}", expected=404)
    corrupted_pdf = args.pdf.with_name("corrupted.pdf")
    invalid_pdf_rejected = False
    if corrupted_pdf.is_file():
        error = upload_pdf(base, corrupted_pdf, expected=422)
        invalid_pdf_rejected = "PDF_VALIDATION" in error["detail"]
        assert invalid_pdf_rejected

    print(json.dumps({
        "status": "PASS", "health": health, "actor_id": actor_id,
        "document_id": document_id, "demand_id": demand_id,
        "match_id": stored_result["id"], "score": result["score"],
        "match_class": result["match_class"], "document_deduplicated": True,
        "invalid_pdf_rejected": invalid_pdf_rejected,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

