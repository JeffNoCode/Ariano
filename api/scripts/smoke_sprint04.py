"""Verify the PDF -> demand -> ranking flow, including after an API restart."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
from uuid import uuid4

from . import smoke_api as smoke


def authenticate(base: str) -> None:
    email = os.environ.get("ARIANO_TEST_ADMIN_EMAIL")
    password = os.environ.get("ARIANO_TEST_ADMIN_PASSWORD") or getpass.getpass("Senha do administrador: ")
    if not email or not password:
        raise SystemExit("Informe ARIANO_TEST_ADMIN_EMAIL e a senha do administrador")
    try:
        login = smoke.call(base, "POST", "/auth/login", {"email": email, "password": password})
    except AssertionError as exc:
        if "HTTP 401" in str(exc):
            raise SystemExit("Conta ADMIN não reconhecida. Confira o e-mail e a senha usados na Sprint 03.") from None
        raise
    smoke.AUTH_TOKEN = login["access_token"]


def create(base: str, pdf: Path) -> dict:
    suffix = uuid4().hex[:8].upper()
    tags = smoke.call(base, "GET", "/tags?only_active=true")
    if not tags:
        tags = [smoke.call(base, "POST", "/tags", {"code": f"S04_{suffix}", "name": "Competência de teste"}, expected=201)]
    tag_id = tags[0]["id"]
    actor = smoke.call(base, "POST", "/actors", {
        "type": "ORGANIZATION", "name": f"Ator Sprint 04 {suffix}",
        "tags": [{"tag_id": tag_id, "weight": 1}],
    }, expected=201)
    document = smoke.upload_pdf(base, pdf)
    demand = smoke.call(base, "POST", "/demands", {
        "title": f"Oportunidade Sprint 04 {suffix}",
        "description": "Fluxo completo de demonstração",
        "document_id": document["id"],
        "tags": [{"tag_id": tag_id, "type": "REQUIRED", "weight": 1}],
    }, expected=201)
    demand_id = demand["id"]
    assert demand_id in {row["id"] for row in smoke.call(base, "GET", "/demands?limit=500")}
    ranking = smoke.call(base, "POST", f"/demands/{demand_id}/match", {"persist": True})
    assert ranking["persisted"] is True
    match = next(row for row in smoke.call(base, "GET", f"/demands/{demand_id}/matches") if row["actor_id"] == actor["id"])
    assert match["score"] > 0
    assert smoke.call(base, "GET", f"/matches/{match['id']}/details")

    invalid = [
        {"title": "Demanda sem competências", "tags": []},
        {"title": "   ", "tags": [{"tag_id": tag_id, "weight": 1}]},
        {"title": "Peso inválido", "tags": [{"tag_id": tag_id, "weight": 0}]},
        {"title": "Tag repetida", "tags": [{"tag_id": tag_id, "weight": 1}, {"tag_id": tag_id, "weight": 1}]},
        {"title": "Orçamento inválido", "budget": -1, "tags": [{"tag_id": tag_id, "weight": 1}]},
    ]
    for payload in invalid:
        smoke.call(base, "POST", "/demands", payload, expected=422)
    corrupted = pdf.with_name("corrupted.pdf")
    if corrupted.is_file():
        error = smoke.upload_pdf(base, corrupted, expected=422)
        assert "PDF_VALIDATION" in error["detail"]
    admin_token = smoke.AUTH_TOKEN
    viewer_email = f"sprint04-{suffix.lower()}@example.invalid"
    smoke.call(base, "POST", "/auth/register", {
        "name": "Leitor Sprint 04", "email": viewer_email,
        "password": "sprint04-local-12345",
    }, expected=201)
    smoke.AUTH_TOKEN = smoke.call(base, "POST", "/auth/login", {
        "email": viewer_email, "password": "sprint04-local-12345",
    })["access_token"]
    try:
        assert demand_id in {row["id"] for row in smoke.call(base, "GET", "/demands?limit=500")}
        smoke.call(base, "POST", "/demands", {
            "title": "Leitor não pode criar", "tags": [{"tag_id": tag_id, "weight": 1}],
        }, expected=403)
        smoke.call(base, "POST", f"/demands/{demand_id}/match", {"persist": True}, expected=403)
    finally:
        smoke.AUTH_TOKEN = admin_token
    return {"status": "PASS", "phase": "create", "demand_id": demand_id, "actor_id": actor["id"],
            "document_id": document["id"], "match_id": match["id"], "score": match["score"],
            "validations_rejected": len(invalid) + int(corrupted.is_file()),
            "viewer_read": 200, "viewer_write": 403}


def verify(base: str, demand_id: int) -> dict:
    demands = smoke.call(base, "GET", "/demands?limit=500")
    assert demand_id in {row["id"] for row in demands}
    demand = smoke.call(base, "GET", f"/demands/{demand_id}")
    document = smoke.call(base, "GET", f"/documents/{demand['document_id']}")
    matches = smoke.call(base, "GET", f"/demands/{demand_id}/matches")
    assert document["id"] == demand["document_id"] and matches and demand["tags"]
    return {"status": "PASS", "phase": "verify_after_restart", "demand_id": demand_id,
            "document_id": document["id"], "persisted_matches": len(matches)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--verify-demand", type=int)
    parser.add_argument("--pdf", type=Path, default=Path(__file__).resolve().parents[2] / "scrapper-py" / "ariano_scraper" / "tests" / "fixtures" / "sample_edital.pdf")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    authenticate(base)
    health = smoke.call(base, "GET", "/health")
    assert health == {"status": "ok", "database": "ok", "engine": "ok"}
    result = verify(base, args.verify_demand) if args.verify_demand else create(base, args.pdf)
    result["health"] = health
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

