from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from . import auth_repository as auth_repo, bootstrap, db, repository as repo, security
from .engine import bindings as engine
from .models import ActorIn, DemandIn, LoginIn, MatchOptions, RegisterIn, RelationIn, RoleUpdateIn, TagIn, TagOut
from .models import DemandStatusName, EngineBenchIn, PdfBenchIn
from .services import bench_service, document_service, matching_service

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
    bootstrap.prepare_database(db.DATABASE_URL)
    db.open_pool()
    engine.get_library()
    yield
    db.close_pool()


app = FastAPI(
    title="ARIANO API",
    version="0.3.0",
    description=API_DESCRIPTION,
    lifespan=lifespan,
)
app.mount("/app", StaticFiles(directory=Path(__file__).resolve().parents[1] / "static", html=True), name="app")


@app.middleware("http")
async def _revalidate_frontend(request, call_next):
    # Sem isso o navegador reaproveita app.js/styles.css antigos depois de um
    # deploy. "no-cache" não impede o cache: só obriga a conferir o ETag.
    response = await call_next(request)
    if request.url.path.startswith("/app"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def get_conn():
    with db.connection() as conn:
        yield conn


bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    conn=Depends(get_conn),
) -> dict:
    if credentials is None:
        raise HTTPException(401, "autenticação necessária", headers={"WWW-Authenticate": "Bearer"})
    user = auth_repo.user_by_session(conn, security.token_hash(credentials.credentials))
    if user is None:
        raise HTTPException(401, "sessão inválida ou expirada", headers={"WWW-Authenticate": "Bearer"})
    return user


def require_role(*roles: str):
    def check(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, "perfil sem permissão para esta operação")
        return user

    return check


editor_required = require_role("ADMIN", "EDITOR")
admin_required = require_role("ADMIN")


@app.exception_handler(repo.NotFound)
async def _not_found(request, exc: repo.NotFound):
    # Um exception handler precisa DEVOLVER a resposta: levantar
    # HTTPException aqui dentro não é tratado e vira erro 500.
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/app/")

@app.get("/health", tags=["infra"], summary="Banco e motor estão de pé?")
def health(conn=Depends(get_conn)) -> dict:
    conn.execute("SELECT 1")
    engine.get_library()
    return {"status": "ok", "database": "ok", "engine": "ok"}


@app.get("/stats", tags=["infra"], summary="Indicadores do painel Visão geral")
def stats(user=Depends(current_user), conn=Depends(get_conn)) -> dict:
    return repo.overview_stats(conn)


@app.get("/bench/info", tags=["desempenho"], summary="CPU do servidor e resultados de referência")
def bench_info(user=Depends(current_user)) -> dict:
    return {
        "server": bench_service.cpu_info(),
        "reference": bench_service.reference(),
        "options": {
            "actors": list(bench_service.ACTOR_CHOICES),
            "threads": list(bench_service.THREAD_CHOICES),
            "concurrency": list(bench_service.CONCURRENCY_CHOICES),
            "pdfs": [p.name for p in bench_service.pdf_files()],
        },
    }


@app.post("/bench/engine", tags=["desempenho"], status_code=202,
          summary="Motor em C: 1 thread x N threads, com progresso ao vivo")
def bench_engine(payload: EngineBenchIn, user=Depends(current_user)) -> dict:
    try:
        return bench_service.start_engine(payload.actors, payload.threads)
    except bench_service.Busy as exc:
        raise HTTPException(409, str(exc))


@app.post("/bench/pdfs", tags=["desempenho"], status_code=202,
          summary="Editais: um de cada vez x N ao mesmo tempo")
def bench_pdfs(payload: PdfBenchIn, user=Depends(current_user)) -> dict:
    try:
        return bench_service.start_pdfs(payload.concurrency)
    except bench_service.Busy as exc:
        raise HTTPException(409, str(exc))


@app.get("/bench/jobs/{job_id}", tags=["desempenho"], summary="Andamento de um teste")
def bench_job(job_id: str, user=Depends(current_user)) -> dict:
    job = bench_service.snapshot(job_id)
    if job is None:
        raise HTTPException(404, "teste não encontrado (o servidor pode ter reiniciado)")
    return job


@app.post("/auth/register", tags=["acesso"], status_code=201)
def register(payload: RegisterIn, conn=Depends(get_conn)):
    try:
        return auth_repo.create_user(
            conn, payload.name.strip(), payload.email.strip().lower(),
            security.hash_password(payload.password),
        )
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "email já cadastrado")


@app.post("/auth/login", tags=["acesso"])
def login(payload: LoginIn, conn=Depends(get_conn)):
    user = auth_repo.user_by_email(conn, payload.email.strip().lower())
    if user is None or not user["is_active"] or not security.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(401, "email ou senha inválidos")
    token = security.new_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=12)
    auth_repo.create_session(conn, security.token_hash(token), user["id"], expires_at)
    conn.commit()
    return {"access_token": token, "token_type": "bearer", "expires_at": expires_at}


@app.get("/auth/me", tags=["acesso"])
def me(user: dict = Depends(current_user)):
    return user


@app.post("/auth/logout", tags=["acesso"])
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    user: dict = Depends(current_user),
    conn=Depends(get_conn),
):
    auth_repo.revoke_session(conn, security.token_hash(credentials.credentials))
    return {"status": "ok"}


@app.get("/users", tags=["usuários"])
def users(user: dict = Depends(admin_required), conn=Depends(get_conn)):
    return auth_repo.list_users(conn)


@app.patch("/users/{user_id}/role", tags=["usuários"])
def change_role(
    user_id: int, payload: RoleUpdateIn, user: dict = Depends(admin_required), conn=Depends(get_conn),
):
    target = conn.execute("SELECT role FROM tb_users WHERE id = %s FOR UPDATE", (user_id,)).fetchone()
    if target is None:
        raise HTTPException(404, "usuário não encontrado")
    if target["role"] == "ADMIN" and payload.role != "ADMIN" and auth_repo.admin_count(conn) <= 1:
        raise HTTPException(409, "não é possível remover o último administrador")
    return auth_repo.set_role(conn, user_id, payload.role)


@app.post("/tags", tags=["tags"], status_code=201, response_model=TagOut)
def create_tag(payload: TagIn, user=Depends(editor_required), conn=Depends(get_conn)):
    try:
        return repo.create_tag(conn, payload.code, payload.name, payload.category, payload.subcategory)
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, f"já existe uma tag com o código {payload.code}")


@app.get("/tags", tags=["tags"], response_model=list[TagOut])
def list_tags(only_active: bool = False, user=Depends(current_user), conn=Depends(get_conn)):
    return repo.list_tags(conn, only_active)


@app.put("/tags/relationships", tags=["tags"], summary="Cria ou atualiza uma relação")
def upsert_relationship(payload: RelationIn, user=Depends(editor_required), conn=Depends(get_conn)):
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
def create_actor(payload: ActorIn, user=Depends(editor_required), conn=Depends(get_conn)):
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
    actor = repo.get_actor(conn, actor_id)
    complete_operation(conn, user, "CREATE", "ACTOR", actor_id)
    return actor


@app.get("/actors", tags=["atores"])
def list_actors(
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    user=Depends(current_user), conn=Depends(get_conn),
):
    return repo.list_actors(conn, limit, offset)


@app.get("/actors/{actor_id}", tags=["atores"])
def get_actor(actor_id: int, user=Depends(current_user), conn=Depends(get_conn)):
    return repo.get_actor(conn, actor_id)


@app.put("/actors/{actor_id}", tags=["atores"])
def update_actor(actor_id: int, payload: ActorIn, user=Depends(editor_required), conn=Depends(get_conn)):
    try:
        actor = repo.update_actor(
            conn, actor_id, actor_type=payload.type, name=payload.name,
            description=payload.description, document=payload.document,
            document_type=payload.document_type, status=payload.status,
            city=payload.city, state=payload.state, profile=payload.profile.model_dump(),
            tags=[(tag.tag_id, tag.weight) for tag in payload.tags],
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(422, "alguma tag informada não existe")
    except psycopg.errors.UniqueViolation:
        raise HTTPException(422, "tag repetida na lista do ator")
    complete_operation(conn, user, "UPDATE", "ACTOR", actor_id)
    return actor


@app.delete("/actors/{actor_id}", tags=["atores"], status_code=204)
def delete_actor(actor_id: int, user=Depends(editor_required), conn=Depends(get_conn)):
    try:
        repo.delete_actor(conn, actor_id)
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(409, "ator vinculado a uma demanda; exclusão não permitida")
    complete_operation(conn, user, "DELETE", "ACTOR", actor_id)


@app.post("/demands", tags=["demandas"], status_code=201)
def create_demand(payload: DemandIn, user=Depends(editor_required), conn=Depends(get_conn)):
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
    demand = repo.get_demand(conn, demand_id)
    complete_operation(conn, user, "CREATE", "DEMAND", demand_id)
    return demand


def opportunity_filters(
    q: str = Query("", max_length=180), status: DemandStatusName | None = None,
    date_from: date | None = None, date_to: date | None = None,
) -> dict:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "A data inicial deve ser anterior ou igual à data final.")
    return {"q": q, "status": status, "date_from": date_from, "date_to": date_to}


@app.get("/demands", tags=["demandas"])
def list_demands(
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    filters=Depends(opportunity_filters), user=Depends(current_user), conn=Depends(get_conn),
):
    return repo.list_demands(conn, limit, offset, **filters)


@app.get("/demands/{demand_id}", tags=["demandas"])
def get_demand(demand_id: int, user=Depends(current_user), conn=Depends(get_conn)):
    return repo.get_demand(conn, demand_id)


@app.post(
    "/demands/{demand_id}/match",
    tags=["matching"],
    summary="Roda o motor e devolve o ranking de atores",
)
def run_match(demand_id: int, options: MatchOptions = MatchOptions(), user=Depends(editor_required), conn=Depends(get_conn)):
    try:
        result = matching_service.run_matching(
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


    if options.persist:
        complete_operation(conn, user, "CALCULATE", "RANKING", demand_id)
    return result


@app.get("/demands/{demand_id}/matches", tags=["matching"], summary="Ranking já gravado")
def stored_matches(
    demand_id: int, limit: int = Query(50, ge=1, le=500), user=Depends(current_user), conn=Depends(get_conn)
):
    repo.get_demand(conn, demand_id)
    return repo.list_matches(conn, demand_id, limit)


@app.get("/matches/{match_id}/details", tags=["matching"], summary="Por que este score?")
def match_details(match_id: int, user=Depends(current_user), conn=Depends(get_conn)):
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
def ingest_document(file: UploadFile = File(...), user=Depends(editor_required), conn=Depends(get_conn)):
    content = file.file.read(10 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(422, "PDF_VALIDATION: o arquivo está vazio")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(422, "PDF_VALIDATION: o PDF deve ter no máximo 10 MB")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(422, "PDF_VALIDATION: selecione um PDF válido")
    try:
        payload = document_service.run_scraper(content, file.filename or "upload.pdf")
    except document_service.ScraperError as exc:
        if exc.returncode == 1:
            raise HTTPException(422, "PDF_VALIDATION: não foi possível ler o PDF. Confira se o arquivo está íntegro e contém texto.")
        raise HTTPException(500, "não foi possível processar o PDF neste momento")
    except TimeoutError:
        raise HTTPException(504, "o scraper excedeu o tempo limite")

    row = repo.insert_document(conn, payload)
    if not row["already_existed"]:
        complete_operation(conn, user, "PROCESS", "DOCUMENT", row["id"])
    return {
        "id": row["id"],
        "document_hash": row["document_hash"],
        "title": row["title"],
        "already_existed": row["already_existed"],
        "extraction_warnings": payload.get("extraction_warnings", []),
        "competencies": payload.get("competencies", []),
    }


@app.get("/documents/{document_id}", tags=["documentos"])
def get_document(document_id: int, user=Depends(current_user), conn=Depends(get_conn)):
    return repo.get_document(conn, document_id)



def complete_operation(conn, user: dict, action: str, entity: str, entity_id: int) -> None:
    # Dados e evento são confirmados juntos antes da resposta de sucesso.
    repo.record_operation(conn, user["id"], action, entity, entity_id)
    conn.commit()


def spreadsheet_text(value: str | None) -> str:
    text = value or ""
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


@app.get("/reports/opportunities.csv", tags=["relatórios"], response_class=Response)
def export_opportunities(filters=Depends(opportunity_filters), user=Depends(current_user), conn=Depends(get_conn)):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID", "Demanda", "Solicitante", "Situação", "Prazo", "Competências", "Resultados", "Melhor score"])
    for row in repo.list_demands(conn, limit=None, **filters):
        writer.writerow([
            row["id"], spreadsheet_text(row["title"]), spreadsheet_text(row["requester_name"]),
            row["status"], row["deadline"], row["tag_count"], row["match_count"], row["best_score"],
        ])
    return Response(
        output.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="oportunidades.csv"', "Cache-Control": "no-store"},
    )


@app.get("/operations", tags=["histórico"])
def list_operations(
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    user=Depends(editor_required), conn=Depends(get_conn),
):
    return repo.list_operations(conn, limit, offset)
