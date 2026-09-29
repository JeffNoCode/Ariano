"""
Orquestra o matching: banco -> motor em C -> banco.

Esta é a única camada que conhece os dois lados. O repositório não sabe que
existe um motor em C; o motor não sabe que existe um banco.
"""

from __future__ import annotations

from psycopg import Connection

from .. import repository as repo
from ..engine import bindings as engine


class DemandHasNoTags(Exception):
    """Demanda sem nenhuma tag: não há o que casar (o motor devolve NOT_EVALUABLE)."""


def candidate_tag_closure(
    demand_tags: list[tuple[int, str, float]], relations: list[dict]
) -> set[int]:
    """
    Tags que um ator pode ter para pontuar > 0 nesta demanda: as exigidas
    (match EXACT) mais as origens das relações que apontam para elas
    (match RELATED). Qualquer outra tag é irrelevante para esta demanda —
    o motor garante que tags extras do ator não alteram o score.
    """
    closure = {tag_id for tag_id, _, _ in demand_tags}
    closure.update(r["source_tag_id"] for r in relations)
    return closure


def run_matching(
    conn: Connection,
    demand_id: int,
    *,
    threshold: float = 0.0,
    top_k: int = 0,
    desirable_share: float = 0.20,
    only_active: bool = True,
    evaluate_all_actors: bool = False,
    persist: bool = False,
) -> dict:
    """
    Calcula o ranking de atores para uma demanda.

    `persist=True` grava em tb_matches (score_details em jsonb), substituindo
    o resultado anterior da mesma versão de algoritmo.
    """
    repo.get_demand(conn, demand_id)  # 404 antes de qualquer trabalho
    demand_tags = repo.demand_tags_for_matching(conn, demand_id)
    if not demand_tags:
        raise DemandHasNoTags(f"demanda {demand_id} não tem tags")

    relations = repo.relations_for_targets(conn, [t[0] for t in demand_tags])

    candidates = (
        None
        if evaluate_all_actors
        else sorted(candidate_tag_closure(demand_tags, relations))
    )
    actor_rows = repo.load_actors_for_matching(
        conn, candidate_tag_ids=candidates, only_active=only_active
    )

    batch = engine.run_batch(
        [
            engine.ActorInput(id=a["id"], tags=a["tags"], type=a["actor_type"], status=a["status"])
            for a in actor_rows
        ],
        engine.DemandInput(id=demand_id, tags=demand_tags),
        [
            engine.RelationInput(
                r["source_tag_id"], r["target_tag_id"], r["relation_type"], r["weight"]
            )
            for r in relations
        ],
        desirable_share=desirable_share,
        threshold=threshold,
        top_k=top_k,
    )

    if persist:
        repo.replace_matches(conn, demand_id, batch.results)

    # Traduz IDs para códigos legíveis, para a resposta da API não obrigar
    # o cliente a fazer um segundo GET /tags.
    ids = {d.demand_tag_id for r in batch.results for d in r.details}
    ids |= {d.actor_tag_id for r in batch.results for d in r.details if d.actor_tag_id}
    codes = repo.tag_codes(conn, sorted(ids))
    names = {a["id"]: a for a in repo.list_actors(conn, limit=10_000)}

    return {
        "demand_id": demand_id,
        "status": batch.status,
        "evaluated_count": batch.evaluated_count,
        "passed_count": batch.passed_count,
        "persisted": persist,
        "results": [
            {
                "actor_id": r.actor_id,
                "actor_name": names.get(r.actor_id, {}).get("name"),
                "score": r.score,
                "match_class": r.match_class,
                "required_score": r.required_score,
                "desirable_score": r.desirable_score,
                "required_count": r.required_count,
                "desirable_count": r.desirable_count,
                "required_missing_count": r.required_missing_count,
                "algorithm_version": r.algorithm_version,
                "details": [
                    {
                        "demand_tag_id": d.demand_tag_id,
                        "demand_tag_code": codes.get(d.demand_tag_id),
                        "tag_type": d.tag_type,
                        "match": d.match,
                        "actor_tag_id": d.actor_tag_id,
                        "actor_tag_code": codes.get(d.actor_tag_id) if d.actor_tag_id else None,
                        "relation_type": d.relation_type,
                        "demand_weight": d.demand_weight,
                        "actor_weight": d.actor_weight,
                        "relation_weight": d.relation_weight,
                        "coverage": d.coverage,
                    }
                    for d in r.details
                ],
            }
            for r in batch.results
        ],
    }
