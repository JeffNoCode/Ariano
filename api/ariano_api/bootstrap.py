"""
Preparação do banco na subida da API.

Em produção (Neon, Render...) não existe o /docker-entrypoint-initdb.d do
Postgres local, nem um terminal para rodar scripts. Por isso a própria API,
ao iniciar, garante que:

1. o schema e as migrações estão aplicados (todos os arquivos são idempotentes:
   CREATE ... IF NOT EXISTS, CREATE OR REPLACE, ON CONFLICT DO NOTHING);
2. o cenário de demonstração (seed.sql + demo.sql, com ranking já calculado)
   existe, só se o banco estiver vazio e ARIANO_SEED_DEMO não for false;
3. existe um administrador, se ARIANO_ADMIN_EMAIL e ARIANO_ADMIN_PASSWORD
   estiverem definidos.

Um advisory lock impede que duas instâncias apliquem as migrações ao mesmo
tempo. Desligue tudo com ARIANO_AUTO_MIGRATE=false.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from . import auth_repository, security

# Logger do uvicorn: já vem configurado e aparece nos logs do Render/Docker.
log = logging.getLogger("uvicorn.error")

DB_DIR = Path(os.environ.get("ARIANO_DB_DIR", Path(__file__).resolve().parents[1] / "db"))
_LOCK_KEY = 4_242_026  # valor arbitrário, só precisa ser fixo


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "sim"}


def migration_files(db_dir: Path = DB_DIR) -> list[Path]:
    """schema.sql primeiro, depois migrations/*.sql em ordem de nome."""
    return [db_dir / "schema.sql", *sorted((db_dir / "migrations").glob("*.sql"))]


def _run_script(conn: psycopg.Connection, path: Path) -> None:
    # Sem parâmetros, o psycopg envia o arquivo inteiro de uma vez, então os
    # BEGIN/COMMIT e as funções plpgsql dos scripts funcionam como no psql.
    conn.execute(path.read_text(encoding="utf-8"))
    log.info("aplicado: %s", path.name)


def _rank_all_demands(conn: psycopg.Connection) -> None:
    """Grava o ranking inicial de cada demanda, para o painel abrir com dados."""
    from .services import matching_service  # import tardio: carrega o motor em C

    ids = [r["id"] for r in conn.execute(
        "SELECT DISTINCT demand_id AS id FROM tb_demand_tags ORDER BY demand_id"
    ).fetchall()]
    for demand_id in ids:
        try:
            # threshold mínimo: não grava quem tem score 0 (nenhuma obrigatória coberta)
            matching_service.run_matching(conn, demand_id, threshold=0.001, persist=True)
        except Exception as exc:  # demonstração não pode impedir a API de subir
            log.warning("ranking inicial da demanda %s falhou: %s", demand_id, exc)
    log.info("ranking inicial gravado para %d demanda(s)", len(ids))


def ensure_admin(conn: psycopg.Connection, email: str, password: str, name: str) -> str:
    if len(password) < 12:
        raise ValueError("ARIANO_ADMIN_PASSWORD precisa ter pelo menos 12 caracteres")
    email = email.strip().lower()
    existing = auth_repository.user_by_email(conn, email)
    if existing is not None:
        # Nunca troca senha nem papel de uma conta existente a partir do ambiente.
        return "existing"
    auth_repository.create_user(conn, name, email, security.hash_password(password), "ADMIN")
    return "created"


def prepare_database(database_url: str) -> None:
    if not _flag("ARIANO_AUTO_MIGRATE", True):
        log.info("ARIANO_AUTO_MIGRATE=false: banco não será alterado na subida")
        return

    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))
        try:
            for path in migration_files():
                _run_script(conn, path)

            empty = conn.execute("SELECT NOT EXISTS (SELECT 1 FROM tb_actors) AS empty").fetchone()["empty"]
            if empty and _flag("ARIANO_SEED_DEMO", True):
                _run_script(conn, DB_DIR / "seed.sql")
                _run_script(conn, DB_DIR / "demo.sql")
                _rank_all_demands(conn)

            email = os.environ.get("ARIANO_ADMIN_EMAIL", "").strip()
            password = os.environ.get("ARIANO_ADMIN_PASSWORD", "")
            if email and password:
                name = os.environ.get("ARIANO_ADMIN_NAME", "Administrador ARIANO")
                result = ensure_admin(conn, email, password, name)
                log.info("administrador %s: %s", email, "criado" if result == "created" else "já existia")
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))
