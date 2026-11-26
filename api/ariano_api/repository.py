
from __future__ import annotations

from datetime import date

import json
from typing import Any, Sequence

from psycopg import Connection
from psycopg.types.json import Jsonb


class NotFound(Exception):
    """A entidade pedida não existe."""

def create_tag(conn: Connection, code: str, name: str, category: str | None, subcategory: str | None) -> dict:
    return conn.execute(
        """
        INSERT INTO tb_tags (code, name, category, subcategory)
        VALUES (%s, %s, %s, %s)
        RETURNING id, code, name, category, subcategory, is_active
        """,
        (code, name, category, subcategory),
    ).fetchone()


def list_tags(conn: Connection, only_active: bool = False) -> list[dict]:
    clause = "WHERE is_active" if only_active else ""
    return conn.execute(
        f"SELECT id, code, name, category, subcategory, is_active FROM tb_tags {clause} ORDER BY code"
    ).fetchall()


def get_tag(conn: Connection, tag_id: int) -> dict:
    row = conn.execute(
        "SELECT id, code, name, category, subcategory, is_active FROM tb_tags WHERE id = %s",
        (tag_id,),
    ).fetchone()
    if row is None:
        raise NotFound(f"tag {tag_id} não existe")
    return row


def tag_codes(conn: Connection, tag_ids: Sequence[int]) -> dict[int, str]:
    """Catálogo id -> code, para traduzir os IDs que o motor devolve."""
    if not tag_ids:
        return {}
    rows = conn.execute(
        "SELECT id, code FROM tb_tags WHERE id = ANY(%s)", (list(tag_ids),)
    ).fetchall()
    return {r["id"]: r["code"] for r in rows}


def upsert_relationship(
    conn: Connection, source_tag_id: int, target_tag_id: int, relation_type: str, weight: float
) -> dict:
    return conn.execute(
        """
        INSERT INTO tb_tag_relationships (source_tag_id, target_tag_id, relation_type, weight)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (source_tag_id, target_tag_id, relation_type)
        DO UPDATE SET weight = EXCLUDED.weight
        RETURNING source_tag_id, target_tag_id, relation_type, weight
        """,
        (source_tag_id, target_tag_id, relation_type, weight),
    ).fetchone()


def relations_for_targets(conn: Connection, target_tag_ids: Sequence[int]) -> list[dict]:
    
    if not target_tag_ids:
        return []
    return conn.execute(
        """
        SELECT source_tag_id, target_tag_id, relation_type, weight
          FROM tb_tag_relationships
         WHERE target_tag_id = ANY(%s)
           AND relation_type <> 'PART_OF'
        """,
        (list(target_tag_ids),),
    ).fetchall()

_SUBTYPE_TABLE = {
    "SOLVER": "tb_solvers",
    "STARTUP": "tb_startups",
    "ORGANIZATION": "tb_organizations",
    "GOVERNMENT_AGENCY": "tb_government_agencies",
}
_SUBTYPE_COLUMNS = {
    "SOLVER": ["bio"],
    "STARTUP": ["sector", "solution_description", "maturity_level"],
    "ORGANIZATION": ["business_sector"],
    "GOVERNMENT_AGENCY": ["agency_type"],
}


def create_actor(
    conn: Connection,
    *,
    actor_type: str,
    name: str,
    description: str | None,
    document: str | None,
    document_type: str | None,
    status: str,
    city: str | None,
    state: str | None,
    profile: dict[str, Any],
    tags: Sequence[tuple[int, float]],
) -> int:
    actor_id = conn.execute(
        """
        INSERT INTO tb_actors (actor_type, name, description, document, document_type,
                               status, city, state)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """,
        (actor_type, name, description, document, document_type, status, city, state),
    ).fetchone()["id"]

    table = _SUBTYPE_TABLE[actor_type]
    columns = _SUBTYPE_COLUMNS[actor_type]
    values = [profile.get(c) for c in columns]
    placeholders = ", ".join(["%s"] * len(columns))
    conn.execute(
        f"INSERT INTO {table} (actor_id, {', '.join(columns)}) VALUES (%s, {placeholders})",
        (actor_id, *values),
    )

    set_actor_tags(conn, actor_id, tags)
    return actor_id


def set_actor_tags(conn: Connection, actor_id: int, tags: Sequence[tuple[int, float]]) -> None:
    conn.execute("DELETE FROM tb_actor_tags WHERE actor_id = %s", (actor_id,))
    if tags:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO tb_actor_tags (actor_id, tag_id, weight) VALUES (%s, %s, %s)",
                [(actor_id, t, w) for t, w in tags],
            )


def update_actor(
    conn: Connection,
    actor_id: int,
    *,
    actor_type: str,
    name: str,
    description: str | None,
    document: str | None,
    document_type: str | None,
    status: str,
    city: str | None,
    state: str | None,
    profile: dict[str, Any],
    tags: Sequence[tuple[int, float]],
) -> dict:
    current = get_actor(conn, actor_id)
    if current["actor_type"] != actor_type:
        raise ValueError("o tipo do ator não pode ser alterado neste cadastro")
    conn.execute(
        """UPDATE tb_actors SET name=%s, description=%s, document=%s,
           document_type=%s, status=%s, city=%s, state=%s, updated_at=now()
           WHERE id=%s""",
        (name, description, document, document_type, status, city, state, actor_id),
    )
    table = _SUBTYPE_TABLE[actor_type]
    columns = _SUBTYPE_COLUMNS[actor_type]
    assignments = ", ".join(f"{column}=%s" for column in columns)
    conn.execute(
        f"UPDATE {table} SET {assignments} WHERE actor_id=%s",
        (*[profile.get(column) for column in columns], actor_id),
    )
    set_actor_tags(conn, actor_id, tags)
    return get_actor(conn, actor_id)


def delete_actor(conn: Connection, actor_id: int) -> None:
    row = conn.execute("DELETE FROM tb_actors WHERE id=%s RETURNING id", (actor_id,)).fetchone()
    if row is None:
        raise NotFound(f"ator {actor_id} não existe")


def get_actor(conn: Connection, actor_id: int) -> dict:
    actor = conn.execute(
        """
        SELECT id, actor_type, name, description, document, document_type, status,
               city, state, created_at, updated_at
          FROM tb_actors WHERE id = %s
        """,
        (actor_id,),
    ).fetchone()
    if actor is None:
        raise NotFound(f"ator {actor_id} não existe")

    table = _SUBTYPE_TABLE[actor["actor_type"]]
    columns = _SUBTYPE_COLUMNS[actor["actor_type"]]
    profile = conn.execute(
        f"SELECT {', '.join(columns)} FROM {table} WHERE actor_id = %s", (actor_id,)
    ).fetchone()
    actor["profile"] = profile or {}

    actor["tags"] = conn.execute(
        """
        SELECT at.tag_id, t.code, at.weight
          FROM tb_actor_tags at JOIN tb_tags t ON t.id = at.tag_id
         WHERE at.actor_id = %s ORDER BY t.code
        """,
        (actor_id,),
    ).fetchall()
    return actor


def list_actors(conn: Connection, limit: int = 50, offset: int = 0) -> list[dict]:
    return conn.execute(
        """
        SELECT a.id, a.actor_type, a.name, a.status, a.city, a.state,
               count(at.tag_id) AS tag_count
          FROM tb_actors a LEFT JOIN tb_actor_tags at ON at.actor_id = a.id
         GROUP BY a.id ORDER BY a.id LIMIT %s OFFSET %s
        """,
        (limit, offset),
    ).fetchall()


def load_actors_for_matching(
    conn: Connection,
    *,
    candidate_tag_ids: Sequence[int] | None,
    only_active: bool = True,
) -> list[dict]:

    params: list[Any] = []
    where = []
    if only_active:
        where.append("a.status = 'ACTIVE'")
    if candidate_tag_ids is not None:
        where.append(
            "EXISTS (SELECT 1 FROM tb_actor_tags f "
            "WHERE f.actor_id = a.id AND f.tag_id = ANY(%s))"
        )
        params.append(list(candidate_tag_ids))

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = conn.execute(
        f"""
        SELECT a.id, a.actor_type, a.status, at.tag_id, at.weight
          FROM tb_actors a
          LEFT JOIN tb_actor_tags at ON at.actor_id = a.id
          {clause}
         ORDER BY a.id
        """,
        params,
    ).fetchall()

    actors: dict[int, dict] = {}
    for r in rows:
        a = actors.setdefault(
            r["id"], {"id": r["id"], "actor_type": r["actor_type"], "status": r["status"], "tags": []}
        )
        if r["tag_id"] is not None:
            a["tags"].append((r["tag_id"], r["weight"]))
    return list(actors.values())

def create_demand(
    conn: Connection,
    *,
    requester_id: int | None,
    title: str,
    description: str | None,
    status: str,
    deadline: Any,
    budget: Any,
    currency: str,
    document_id: int | None,
    tags: Sequence[tuple[int, str, float]],
) -> int:
    demand_id = conn.execute(
        """
        INSERT INTO tb_demands (requester_id, title, description, status, deadline,
                                budget, currency, document_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """,
        (requester_id, title, description, status, deadline, budget, currency, document_id),
    ).fetchone()["id"]
    if tags:
        insert_demand_tags(conn, demand_id, tags)
    return demand_id


def lock_demand(conn: Connection, demand_id: int) -> str:
    row = conn.execute(
        "SELECT status FROM tb_demands WHERE id = %s FOR UPDATE", (demand_id,),
    ).fetchone()
    if row is None:
        raise NotFound(f"demanda {demand_id} não existe")
    return row["status"]


def update_demand(
    conn: Connection, demand_id: int, *, requester_id: int | None, title: str,
    description: str | None, status: str, deadline: Any, budget: Any, currency: str,
    document_id: int | None, tags: Sequence[tuple[int, str, float]],
) -> None:
    lock_demand(conn, demand_id)
    existing_tags = demand_tags_for_matching(conn, demand_id)
    conn.execute(
        """
        UPDATE tb_demands SET requester_id = %s, title = %s, description = %s,
            status = %s, deadline = %s, budget = %s, currency = %s,
            document_id = %s, updated_at = now() WHERE id = %s
        """,
        (requester_id, title, description, status, deadline, budget, currency, document_id, demand_id),
    )
    if sorted(existing_tags) != sorted(tags):
        conn.execute("DELETE FROM tb_demand_tags WHERE demand_id = %s", (demand_id,))
        insert_demand_tags(conn, demand_id, tags)
        conn.execute("DELETE FROM tb_matches WHERE demand_id = %s", (demand_id,))


def insert_demand_tags(conn: Connection, demand_id: int, tags: Sequence[tuple[int, str, float]]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO tb_demand_tags (demand_id, tag_id, tag_type, weight) VALUES (%s, %s, %s, %s)",
            [(demand_id, tag_id, kind, weight) for tag_id, kind, weight in tags],
        )


def get_demand(conn: Connection, demand_id: int) -> dict:
    demand = conn.execute(
        """
        SELECT id, requester_id, title, description, status, deadline, budget,
               currency, document_id, created_at, updated_at
          FROM tb_demands WHERE id = %s
        """,
        (demand_id,),
    ).fetchone()
    if demand is None:
        raise NotFound(f"demanda {demand_id} não existe")
    demand["tags"] = conn.execute(
        """
        SELECT dt.tag_id, t.code, dt.tag_type, dt.weight
          FROM tb_demand_tags dt JOIN tb_tags t ON t.id = dt.tag_id
         WHERE dt.demand_id = %s ORDER BY dt.tag_type, t.code
        """,
        (demand_id,),
    ).fetchall()
    return demand


def list_demands(
    conn: Connection, limit: int | None = 50, offset: int = 0, *,
    q: str = "", status: str | None = None, date_from: date | None = None, date_to: date | None = None,
) -> list[dict]:
    conditions, params = [], []
    if q.strip():
        conditions.append("strpos(lower(concat_ws(' ', d.title, a.name)), lower(%s)) > 0")
        params.append(q.strip())
    if status is not None:
        conditions.append("d.status = %s")
        params.append(status)
    if date_from is not None:
        conditions.append("d.created_at >= (%s::date::timestamp AT TIME ZONE 'America/Recife')")
        params.append(date_from)
    if date_to is not None:
        conditions.append("d.created_at < ((%s::date + 1)::timestamp AT TIME ZONE 'America/Recife')")
        params.append(date_to)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    return conn.execute(
        f"""
        SELECT d.id, d.title, d.status, d.deadline, d.budget, d.currency,
               d.document_id, d.created_at, a.name AS requester_name,
               count(DISTINCT dt.tag_id) AS tag_count,
               count(DISTINCT m.id) AS match_count,
               max(m.score) AS best_score
          FROM tb_demands d
          LEFT JOIN tb_actors a ON a.id = d.requester_id
          LEFT JOIN tb_demand_tags dt ON dt.demand_id = d.id
          LEFT JOIN tb_matches m ON m.demand_id = d.id
         {where}
         GROUP BY d.id, a.name
         ORDER BY d.created_at DESC, d.id DESC
         LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    ).fetchall()


def overview_stats(conn: Connection) -> dict:
    """Indicadores do painel Visão geral, numa única ida ao banco."""
    return conn.execute(
        """
        SELECT (SELECT count(*) FROM tb_documents)                        AS documents,
               (SELECT count(*) FROM tb_demands)                          AS demands,
               (SELECT count(*) FROM tb_demands WHERE status = 'OPEN')    AS open_demands,
               (SELECT count(*) FROM tb_actors)                           AS actors,
               (SELECT count(*) FROM tb_actors WHERE status = 'ACTIVE')   AS active_actors,
               (SELECT count(*) FROM tb_tags WHERE is_active)             AS tags,
               (SELECT count(*) FROM tb_matches)                          AS matches,
               (SELECT count(*) FROM tb_actors WHERE actor_type = 'SOLVER')            AS solvers,
               (SELECT count(*) FROM tb_actors WHERE actor_type = 'STARTUP')           AS startups,
               (SELECT count(*) FROM tb_actors WHERE actor_type = 'ORGANIZATION')      AS organizations,
               (SELECT count(*) FROM tb_actors WHERE actor_type = 'GOVERNMENT_AGENCY') AS government_agencies
        """
    ).fetchone()


def demand_tags_for_matching(conn: Connection, demand_id: int) -> list[tuple[int, str, float]]:
    rows = conn.execute(
        "SELECT tag_id, tag_type, weight FROM tb_demand_tags WHERE demand_id = %s ORDER BY tag_id",
        (demand_id,),
    ).fetchall()
    return [(r["tag_id"], r["tag_type"], r["weight"]) for r in rows]

def find_document_for_ingest(conn: Connection, document_hash: str) -> dict | None:
    # A espera ocorre antes da leitura do PDF e dura até o commit ou rollback do envio.
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (document_hash,))
    return conn.execute(
        "SELECT id, document_hash, title, payload FROM tb_documents WHERE document_hash = %s",
        (document_hash,),
    ).fetchone()


def insert_document(conn: Connection, payload: dict) -> dict:

    meta = payload.get("processing_metadata", {})
    doc = payload.get("document", {})

    def field(name: str):
        v = doc.get(name)
        return v.get("value") if isinstance(v, dict) else v

    row = conn.execute(
        """
        INSERT INTO tb_documents (source_file, source_url, document_hash, title,
                                  organization, parser_version, extraction_method,
                                  ocr_used, page_count, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (document_hash) DO NOTHING
        RETURNING id, document_hash, title, processed_at
        """,
        (
            meta.get("source_file"),
            meta.get("source_url"),
            meta.get("document_hash"),
            field("title"),
            field("organization"),
            meta.get("parser_version", "unknown"),
            meta.get("extraction_method", "unknown"),
            bool(meta.get("ocr_used", False)),
            meta.get("page_count"),
            Jsonb(payload),
        ),
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT id, document_hash, title, processed_at FROM tb_documents "
            "WHERE document_hash = %s",
            (meta.get("document_hash"),),
        ).fetchone()
        row["already_existed"] = True
    else:
        row["already_existed"] = False
    return row


def get_document(conn: Connection, document_id: int) -> dict:
    row = conn.execute(
        "SELECT id, document_hash, title, organization, payload, processed_at "
        "FROM tb_documents WHERE id = %s",
        (document_id,),
    ).fetchone()
    if row is None:
        raise NotFound(f"documento {document_id} não existe")
    return row

def _detail_to_json(d: Any) -> dict:
    return {
        "demand_tag_id": d.demand_tag_id,
        "tag_type": d.tag_type,
        "match": d.match,
        "actor_tag_id": d.actor_tag_id,
        "relation_type": d.relation_type,
        "demand_weight": d.demand_weight,
        "actor_weight": d.actor_weight,
        "relation_weight": d.relation_weight,
        "coverage": d.coverage,
    }


def replace_matches(conn: Connection, demand_id: int, version: str, results: Sequence[Any]) -> int:
    conn.execute(
        "DELETE FROM tb_matches WHERE demand_id = %s AND algorithm_version = %s",
        (demand_id, version),
    )
    if not results:
        return 0
    rows = [
        (
            demand_id,
            r.actor_id,
            r.score,
            r.match_class,
            Jsonb(
                {
                    "status": r.status,
                    "required_score": r.required_score,
                    "desirable_score": r.desirable_score,
                    "required_count": r.required_count,
                    "desirable_count": r.desirable_count,
                    "required_missing_count": r.required_missing_count,
                    "details": [_detail_to_json(d) for d in r.details],
                }
            ),
            r.algorithm_version,
        )
        for r in results
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO tb_matches (demand_id, actor_id, score, match_type,
                                    score_details, algorithm_version)
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            rows,
        )
    return len(results)


def list_matches(conn: Connection, demand_id: int, limit: int = 50, *, version: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT m.id, m.actor_id, a.name AS actor_name, m.score, m.match_type,
               m.score_details, m.algorithm_version, m.created_at
          FROM tb_matches m JOIN tb_actors a ON a.id = m.actor_id
         WHERE m.demand_id = %s AND m.algorithm_version = %s
         ORDER BY m.score DESC, (m.score_details ->> 'required_missing_count')::integer ASC NULLS LAST, m.actor_id
         LIMIT %s
        """,
        (demand_id, version, limit),
    ).fetchall()
    for r in rows:
        r["required_missing_count"] = r["score_details"].get("required_missing_count")
    return rows


def get_match_details(conn: Connection, match_id: int) -> list[dict] | None:
    row = conn.execute(
        "SELECT score_details FROM tb_matches WHERE id = %s", (match_id,)
    ).fetchone()
    if row is None:
        return None
    details = row["score_details"].get("details", [])
    ids = {d["demand_tag_id"] for d in details} | {
        d["actor_tag_id"] for d in details if d.get("actor_tag_id")
    }
    codes = tag_codes(conn, sorted(ids))
    for d in details:
        d["demand_tag_code"] = codes.get(d["demand_tag_id"])
        d["actor_tag_code"] = codes.get(d["actor_tag_id"]) if d.get("actor_tag_id") else None
    return details



def record_operation(conn: Connection, user_id: int, action: str, entity: str, entity_id: int) -> None:
    conn.execute(
        "INSERT INTO tb_operation_log (user_id, action, entity, entity_id) VALUES (%s, %s, %s, %s)",
        (user_id, action, entity, entity_id),
    )


def list_operations(conn: Connection, limit: int, offset: int) -> list[dict]:
    return conn.execute(
        """
        SELECT l.id, l.action, l.entity, l.entity_id, l.created_at, u.name AS user_name
          FROM tb_operation_log l LEFT JOIN tb_users u ON u.id = l.user_id
         ORDER BY l.created_at DESC, l.id DESC LIMIT %s OFFSET %s
        """,
        (limit, offset),
    ).fetchall()
