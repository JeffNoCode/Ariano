from __future__ import annotations

import asyncio
import json

import pytest

from ariano_api import bootstrap, main, repository as repo


def test_migrations_run_schema_first_then_numbered_files():
    names = [p.name for p in bootstrap.migration_files()]
    assert names[0] == "schema.sql"
    assert names[1:] == sorted(names[1:])
    assert "003_auth.sql" in names and "004_scraper_catalog.sql" in names
    assert "seed.sql" not in names  # o seed só roda com o banco vazio
    assert "demo.sql" not in names


def test_not_found_handler_returns_404_instead_of_raising():
    response = asyncio.run(main._not_found(None, repo.NotFound("demanda 99 não existe")))
    assert response.status_code == 404
    assert json.loads(response.body) == {"detail": "demanda 99 não existe"}


def test_admin_password_from_environment_needs_12_chars():
    with pytest.raises(ValueError):
        bootstrap.ensure_admin(None, "admin@ariano.local", "curta", "Admin")


def test_root_redirects_to_app():
    assert main.root().headers["location"] == "/app/"
