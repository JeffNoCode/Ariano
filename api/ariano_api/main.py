from __future__ import annotations

from contextlib import asynccontextmanager

import psycopg
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile

from . import db, repository as repo
from .engine import bindings as engine
from .models import ActorIn, DemandIn, MatchOptions, RelationIn, TagIn, TagOut
from .services import document_service, matching_service

API_DESCRIPTION = """
Matching entre **atores** (quem tem competências) e **demandas** (quem precisa
delas), com os scores calculados pelo motor em C.

Pontos que valem ler antes de usar:

* Cada ator tem um `type` (SOLVER/STARTUP/ORGANIZATION/GOVERNMENT_AGENCY) e um
  `profile` com os campos específicos daquele subtipo — preencha só os que
  correspondem ao tipo escolhido.
* As relações entre tags são **direcionadas**: `A → B` significa que possuir A
  é evidência de compatibilidade com B. A volta não é automática.
* Scores só são comparáveis **dentro da mesma demanda** — a forma da demanda
  (ter ou não DESIRABLE) define o teto alcançável.
* `match_class` descreve o **tipo** de cobertura (EXACT/RELATED/PARTIAL/NONE),
  não a força dela. A força está no `score`.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.open_pool()
    engine.get_library()
    yield
    db.close_pool()


app = FastAPI(
    title="ARIANO API",
    version="0.2.0",
    description=API_DESCRIPTION,
    lifespan=lifespan,
)


def get_conn():
    with db.connection() as conn:
        yield conn


@app.exception_handler(repo.NotFound)
async def _not_found(request, exc: repo.NotFound):
    raise HTTPException(status_code=404, detail=str(exc))

@app.get("/health", tags=["infra"], summary="Banco e motor estão de pé?")
def health(conn=Depends(get_conn)) -> dict:
    conn.execute("SELECT 1")
    engine.get_library()
    return {"status": "ok", "database": "ok", "engine": "ok"}


@app.post("/tags", tags=["tags"], status_code=201, response_model=TagOut)
def create_tag(payload: TagIn, conn=Depends(get_conn)):
    try:
        return repo.create_tag(conn, payload.code, payload.name, payload.category, payload.subcategory)
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, f"já existe uma tag com o código {payload.code}")


@app.get("/tags", tags=["tags"], response_model=list[TagOut])
def list_tags(only_active: bool = False, conn=Depends(get_conn)):
    return repo.list_tags(conn, only_active)


@app.put("/tags/relationships", tags=["tags"], summary="Cria ou atualiza uma relação")
def upsert_relationship(payload: RelationIn, conn=Depends(get_conn)):
    if payload.source_tag_id == payload.target_tag_id:
        raise HTTPException(422, "uma tag não pode se relacionar consigo mesma")
    try:
        return repo.upsert_relationship(
            conn,
            payload.source_tag_id,
            payload.target_tag_id,
            payload.relation_type,
            payload.weight,
        )
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(422, "source_tag_id ou target_tag_id não existe")


@app.post("/actors", tags=["atores"], status_code=201)
def create_actor(payload: ActorIn, conn=Depends(get_conn)):
    try:
        actor_id = repo.create_actor(
            conn,
            actor_type=payload.type,
            name=payload.name,
            description=payload.description,
            document=payload.document,
            document_type=payload.document_type,
            status=payload.status,
            city=payload.city,
            state=payload.state,
            profile=payload.profile.model_dump(),
            tags=[(t.tag_id, t.weight) for t in payload.tags],
        )
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(422, "alguma tag informada não existe")
    except psycopg.errors.UniqueViolation:
        raise HTTPException(422, "tag repetida na lista do ator")
    return repo.get_actor(conn, actor_id)


@app.get("/actors", tags=["atores"])
def list_actors(
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), conn=Depends(get_conn)
):
    return repo.list_actors(conn, limit, offset)


@app.get("/actors/{actor_id}", tags=["atores"])
def get_actor(actor_id: int, conn=Depends(get_conn)):
    return repo.get_actor(conn, actor_id)


@app.post("/demands", tags=["demandas"], status_code=201)
def create_demand(payload: DemandIn, conn=Depends(get_conn)):
    try:
        demand_id = repo.create_demand(
            conn,
            requester_id=payload.requester_id,
            title=payload.title,
            description=payload.description,
            status=payload.status,
            deadline=payload.deadline,
            budget=payload.budget,
            currency=payload.currency,
            document_id=payload.document_id,
            tags=[(t.tag_id, t.type, t.weight) for t in payload.tags],
        )
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(
            422, "requester_id, document_id ou alguma tag informada não existe"
        )
    return repo.get_demand(conn, demand_id)


@app.get("/demands/{demand_id}", tags=["demandas"])
def get_demand(demand_id: int, conn=Depends(get_conn)):
    return repo.get_demand(conn, demand_id)


@app.post(
    "/demands/{demand_id}/match",
    tags=["matching"],
    summary="Roda o motor e devolve o ranking de atores",
)
def run_match(demand_id: int, options: MatchOptions = MatchOptions(), conn=Depends(get_conn)):
    try:
        return matching_service.run_matching(
            conn,
            demand_id,
            threshold=options.threshold,
            top_k=options.top_k,
            desirable_share=options.desirable_share,
            only_active=options.only_active,
            evaluate_all_actors=options.evaluate_all_actors,
            persist=options.persist,
        )
    except matching_service.DemandHasNoTags as exc:
        raise HTTPException(422, str(exc))
    except engine.MatcherFailure as exc:
        raise HTTPException(
            500,
            {
                "error": "o motor de matching rejeitou os dados",
                "engine_error": exc.name,
                "actor_id": exc.failed_actor_id,
            },
        )


@app.get("/demands/{demand_id}/matches", tags=["matching"], summary="Ranking já gravado")
def stored_matches(
    demand_id: int, limit: int = Query(50, ge=1, le=500), conn=Depends(get_conn)
):
    repo.get_demand(conn, demand_id)
    return repo.list_matches(conn, demand_id, limit)


@app.get("/matches/{match_id}/details", tags=["matching"], summary="Por que este score?")
def match_details(match_id: int, conn=Depends(get_conn)):
    details = repo.get_match_details(conn, match_id)
    if details is None:
        raise HTTPException(404, f"match {match_id} não existe")
    return details

@app.post(
    "/documents",
    tags=["documentos"],
    status_code=201,
    summary="Envia um PDF, roda o scraper e guarda o JSON",
)
def ingest_document(file: UploadFile = File(...), conn=Depends(get_conn)):
    content = file.file.read()
    if not content:
        raise HTTPException(422, "arquivo vazio")
    try:
        payload = document_service.run_scraper(content, file.filename or "upload.pdf")
    except document_service.ScraperError as exc:
    
        raise HTTPException(422 if exc.returncode == 1 else 500, str(exc))
    except TimeoutError:
        raise HTTPException(504, "o scraper excedeu o tempo limite")

    row = repo.insert_document(conn, payload)
    return {
        "id": row["id"],
        "document_hash": row["document_hash"],
        "title": row["title"],
        "already_existed": row["already_existed"],
        "extraction_warnings": payload.get("extraction_warnings", []),
        "competencies": payload.get("competencies", []),
    }


@app.get("/documents/{document_id}", tags=["documentos"])
def get_document(document_id: int, conn=Depends(get_conn)):
    return repo.get_document(conn, document_id)
