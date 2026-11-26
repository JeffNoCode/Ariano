"""Verifica ciclo da demanda, filtros, CSV e histórico com uma API de teste."""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from . import smoke_api as smoke
from .smoke_sprint04 import authenticate


def main() -> None:
    base = os.environ.get("ARIANO_TEST_URL", "http://127.0.0.1:8000").rstrip("/")
    authenticate(base)
    tags = smoke.call(base, "GET", "/tags")
    tag_id = next(row["id"] for row in tags if row["code"] == "MACHINE_LEARNING")
    title = f"Relatório Sprint 09 {uuid4().hex[:8]}"
    payload = {"title": title, "tags": [{"tag_id": tag_id, "type": "REQUIRED", "weight": 1}]}
    demand = smoke.call(base, "POST", "/demands", payload, expected=201)
    demand_id = demand["id"]
    route = f"/demands/{demand_id}"
    ranking = smoke.call(base, "POST", route + "/match", {"persist": True})
    assert ranking["persisted"] and ranking["results"]
    stored = smoke.call(base, "GET", route + "/matches")
    assert stored and stored[0]["score_details"]["details"]

    smoke.call(base, "PUT", route, {**payload, "status": "CLOSED"})
    smoke.call(base, "POST", route + "/match", {"persist": True}, expected=409)
    assert smoke.call(base, "GET", route + "/matches") == stored

    created_date = datetime.fromisoformat(demand["created_at"]).date()
    query = urlencode({
        "q": title, "status": "CLOSED",
        "date_from": created_date - timedelta(days=1), "date_to": created_date + timedelta(days=1),
    })
    rows = smoke.call(base, "GET", "/demands?" + query)
    assert [row["id"] for row in rows] == [demand_id]
    request = Request(
        base + "/reports/opportunities.csv?" + query,
        headers={"Authorization": f"Bearer {smoke.AUTH_TOKEN}"},
    )
    with urlopen(request, timeout=20) as response:
        assert response.headers.get_content_type() == "text/csv"
        csv_rows = list(csv.DictReader(io.StringIO(response.read().decode("utf-8-sig")), delimiter=";"))
    assert [(row["ID"], row["Demanda"], row["Situação"]) for row in csv_rows] == [
        (str(demand_id), title, "CLOSED"),
    ]
    smoke.call(base, "GET", "/demands?date_from=2030-02-02&date_to=2030-02-01", expected=422)

    events = smoke.call(base, "GET", "/operations?limit=100")
    assert any(row["entity"] == "DEMAND" and row["entity_id"] == demand_id and row["action"] == "UPDATE" for row in events)
    assert any(row["entity"] == "RANKING" and row["entity_id"] == demand_id and row["action"] == "CALCULATE" for row in events)
    print(json.dumps({
        "status": "PASS", "demand_id": demand_id, "stored_matches": len(stored),
        "closed_calculation_http": 409, "inverted_dates_http": 422,
        "filtered_rows": len(rows), "csv_rows": len(csv_rows), "history": "verified",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
