"""End-to-end checks for Sprint 03 authentication, roles and actor CRUD."""

from __future__ import annotations

import json
import os
import secrets
import getpass
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def call(base: str, method: str, path: str, payload=None, *, token=None, expected=200):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(base + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            status, body = response.status, response.read()
    except HTTPError as exc:
        status, body = exc.code, exc.read()
    if status != expected:
        raise AssertionError(f"{method} {path}: HTTP {status}, esperado {expected}; {body[:500]!r}")
    return json.loads(body) if body else None


def main() -> None:
    base = os.environ.get("ARIANO_TEST_URL", "http://127.0.0.1:8000").rstrip("/")
    admin_email = os.environ.get("ARIANO_TEST_ADMIN_EMAIL")
    admin_password = os.environ.get("ARIANO_TEST_ADMIN_PASSWORD") or getpass.getpass("Senha do administrador: ")
    if not admin_email or not admin_password:
        raise SystemExit("Defina ARIANO_TEST_ADMIN_EMAIL e informe a senha")

    health = call(base, "GET", "/health")
    assert health == {"status": "ok", "database": "ok", "engine": "ok"}
    call(base, "GET", "/actors", expected=401)
    call(base, "POST", "/auth/login", {"email": admin_email, "password": "senha-incorreta"}, expected=401)
    admin_token = call(base, "POST", "/auth/login", {
        "email": admin_email, "password": admin_password,
    })["access_token"]
    assert call(base, "GET", "/auth/me", token=admin_token)["role"] == "ADMIN"

    suffix = secrets.token_hex(5)
    email = f"sprint03-{suffix}@example.test"
    password = secrets.token_urlsafe(24)
    registered = call(base, "POST", "/auth/register", {
        "name": "Usuário de teste", "email": email, "password": password,
    }, expected=201)
    assert registered["role"] == "VIEWER" and "password_hash" not in registered
    user_id = registered["id"]
    viewer_token = call(base, "POST", "/auth/login", {
        "email": email, "password": password,
    })["access_token"]
    assert call(base, "GET", "/auth/me", token=viewer_token)["role"] == "VIEWER"
    call(base, "GET", "/actors", token=viewer_token)
    call(base, "GET", "/users", token=viewer_token, expected=403)
    call(base, "POST", "/actors", {"type": "ORGANIZATION", "name": "Negado"},
         token=viewer_token, expected=403)

    users = call(base, "GET", "/users", token=admin_token)
    assert any(row["id"] == user_id for row in users)
    changed = call(base, "PATCH", f"/users/{user_id}/role", {"role": "EDITOR"}, token=admin_token)
    assert changed["role"] == "EDITOR"
    assert call(base, "GET", "/auth/me", token=viewer_token)["role"] == "EDITOR"

    actor = call(base, "POST", "/actors", {
        "type": "ORGANIZATION", "name": f"Organização Sprint 03 {suffix}",
        "profile": {"business_sector": "Pesquisa"}, "city": "Recife", "state": "PE",
    }, token=viewer_token, expected=201)
    actor_id = actor["id"]
    assert call(base, "GET", f"/actors/{actor_id}", token=viewer_token)["name"] == actor["name"]
    updated = call(base, "PUT", f"/actors/{actor_id}", {
        "type": "ORGANIZATION", "name": f"Organização Sprint 03 editada {suffix}",
        "profile": {"business_sector": "Tecnologia"}, "city": "Olinda", "state": "PE",
    }, token=viewer_token)
    assert updated["city"] == "Olinda" and updated["profile"]["business_sector"] == "Tecnologia"
    assert call(base, "GET", f"/actors/{actor_id}", token=viewer_token)["name"] == updated["name"]
    call(base, "DELETE", f"/actors/{actor_id}", token=viewer_token, expected=204)
    call(base, "GET", f"/actors/{actor_id}", token=viewer_token, expected=404)

    changed = call(base, "PATCH", f"/users/{user_id}/role", {"role": "VIEWER"}, token=admin_token)
    assert changed["role"] == "VIEWER"
    call(base, "POST", "/actors", {"type": "ORGANIZATION", "name": "Negado outra vez"},
         token=viewer_token, expected=403)
    call(base, "POST", "/auth/logout", token=viewer_token)
    call(base, "GET", "/auth/me", token=viewer_token, expected=401)

    print(json.dumps({
        "status": "PASS", "database_and_engine": health,
        "registration": "VIEWER persisted", "login": "ok", "role_change": "VIEWER -> EDITOR -> VIEWER",
        "viewer_write": "403", "admin_users": "200", "actor_crud": "create/read/update/delete verified",
        "deleted_actor": "404", "logout": "session revoked", "user_id": user_id,
        "actor_id": actor_id,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

