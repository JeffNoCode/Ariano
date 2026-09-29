"""
Ponte ctypes com o motor de matching em C (libariano.so ou libariano.dll).

Os structs abaixo espelham include/domain.h, matcher.h e batch.h campo a
campo, na mesma ordem. Se qualquer header mudar, este arquivo precisa mudar
junto — tests/test_abi.py compara sizeof/offsetof com o C real e falha se as
duas definições saírem de sincronia.

Regras de ownership respeitadas aqui:
  - Actor, Demand e RelationSet são views somente-leitura. Os arrays ctypes
    que os alimentam precisam continuar vivos enquanto a chamada durar — por
    isso build_* devolve também os arrays, e o chamador os mantém em escopo.
  - BatchResult é dono da memória. Sempre liberado com batch_result_free(),
    dentro de um try/finally.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import POINTER, byref, c_char, c_char_p, c_double, c_int, c_int64, c_size_t
from pathlib import Path
from typing import Iterable, NamedTuple

TAG_CODE_MAX = 64
TAG_ID_NONE = -1
BATCH_TOP_K_UNLIMITED = 0

# ------------------------------------------------------------------ enums

ACTOR_TYPE = {"SOLVER": 0, "STARTUP": 1, "ORGANIZATION": 2, "GOVERNMENT_AGENCY": 3}
ACTOR_STATUS = {"ACTIVE": 0, "INACTIVE": 1, "SUSPENDED": 2}
TAG_TYPE = {"REQUIRED": 0, "DESIRABLE": 1}
RELATION_TYPE = {"NONE": 0, "RELATED": 1, "SYNONYM": 2, "PART_OF": 3}

MATCH_TYPE_NAME = {0: "MISSING", 1: "RELATED", 2: "EXACT"}
MATCH_CLASS_NAME = {0: "NONE", 1: "PARTIAL", 2: "RELATED", 3: "EXACT"}
MATCH_STATUS_NAME = {0: "EVALUATED", 1: "NOT_EVALUABLE"}
RELATION_TYPE_NAME = {v: k for k, v in RELATION_TYPE.items()}

MATCHER_OK = 0
MATCHER_ERROR_NAME = {
    0: "OK",
    1: "NULL_ARG",
    2: "INVALID_CONFIG",
    3: "INVALID_TAG_ID",
    4: "INVALID_WEIGHT",
    5: "INVALID_TAG_TYPE",
    6: "DUPLICATE_TAG",
    7: "NO_MEMORY",
    8: "INVALID_OPTIONS",
    9: "DUPLICATE_ACTOR",
}


class MatcherFailure(RuntimeError):
    """Erro devolvido pelo motor. `failed_actor_id` é None quando não é de um ator."""

    def __init__(self, code: int, failed_actor_id: int | None = None):
        self.code = code
        self.name = MATCHER_ERROR_NAME.get(code, f"UNKNOWN_{code}")
        self.failed_actor_id = failed_actor_id
        detail = f" (actor_id={failed_actor_id})" if failed_actor_id is not None else ""
        super().__init__(f"matching engine: {self.name}{detail}")


# ---------------------------------------------------------------- structs


class Tag(ctypes.Structure):
    _fields_ = [("id", c_int64), ("code", c_char * TAG_CODE_MAX)]


class TagCatalog(ctypes.Structure):
    _fields_ = [("items", POINTER(Tag)), ("count", c_size_t)]


class ActorTag(ctypes.Structure):
    _fields_ = [("tag_id", c_int64), ("weight", c_double)]


class Actor(ctypes.Structure):
    _fields_ = [
        ("id", c_int64),
        ("type", c_int),
        ("status", c_int),
        ("tags", POINTER(ActorTag)),
        ("tag_count", c_size_t),
    ]


class DemandTag(ctypes.Structure):
    _fields_ = [("tag_id", c_int64), ("type", c_int), ("weight", c_double)]


class Demand(ctypes.Structure):
    _fields_ = [("id", c_int64), ("tags", POINTER(DemandTag)), ("tag_count", c_size_t)]


class TagRelationship(ctypes.Structure):
    _fields_ = [
        ("source_tag_id", c_int64),
        ("target_tag_id", c_int64),
        ("type", c_int),
        ("weight", c_double),
    ]


class RelationSet(ctypes.Structure):
    _fields_ = [("items", POINTER(TagRelationship)), ("count", c_size_t)]


class MatchDetail(ctypes.Structure):
    _fields_ = [
        ("demand_tag_id", c_int64),
        ("tag_type", c_int),
        ("match", c_int),
        ("actor_tag_id", c_int64),
        ("relation_type", c_int),
        ("demand_weight", c_double),
        ("actor_weight", c_double),
        ("relation_weight", c_double),
        ("coverage", c_double),
    ]


class MatchResult(ctypes.Structure):
    _fields_ = [
        ("actor_id", c_int64),
        ("demand_id", c_int64),
        ("status", c_int),
        ("score", c_double),
        ("required_score", c_double),
        ("desirable_score", c_double),
        ("match_class", c_int),
        ("required_count", c_size_t),
        ("desirable_count", c_size_t),
        ("required_missing_count", c_size_t),
        ("details", POINTER(MatchDetail)),
        ("algorithm_version", c_char_p),
    ]


class MatchConfig(ctypes.Structure):
    _fields_ = [("desirable_share", c_double)]


class BatchOptions(ctypes.Structure):
    _fields_ = [("threshold", c_double), ("top_k", c_size_t)]


class BatchResult(ctypes.Structure):
    _fields_ = [
        ("status", c_int),
        ("evaluated_count", c_size_t),
        ("passed_count", c_size_t),
        ("count", c_size_t),
        ("results", POINTER(MatchResult)),
    ]


# ------------------------------------------------------------ carregamento


def _default_library_path() -> Path:
    env = os.environ.get("ARIANO_ENGINE_LIB")
    if env:
        return Path(env)
    # api/ariano_api/engine/bindings.py -> raiz do repositório
    root = Path(__file__).resolve().parents[3]
    suffix = ".dll" if os.name == "nt" else ".so"
    return root / "Matching-ariano-c" / "matching_engine" / "build" / f"libariano{suffix}"


def load_library(path: str | os.PathLike[str] | None = None) -> ctypes.CDLL:
    lib_path = Path(path) if path else _default_library_path()
    if not lib_path.exists():
        raise FileNotFoundError(
            f"Biblioteca do motor não encontrada em {lib_path}. "
            "Compile com `make shared` em Matching-ariano-c/matching_engine, "
            "ou aponte ARIANO_ENGINE_LIB para o arquivo."
        )
    lib = ctypes.CDLL(str(lib_path))

    lib.batch_match.restype = c_int
    lib.batch_match.argtypes = [
        POINTER(Actor),
        c_size_t,
        POINTER(Demand),
        POINTER(RelationSet),
        POINTER(MatchConfig),
        POINTER(BatchOptions),
        POINTER(BatchResult),
        POINTER(c_int64),
    ]
    lib.batch_result_free.restype = None
    lib.batch_result_free.argtypes = [POINTER(BatchResult)]

    lib.matcher_default_config.restype = MatchConfig
    lib.matcher_default_config.argtypes = []
    lib.batch_default_options.restype = BatchOptions
    lib.batch_default_options.argtypes = []
    lib.matcher_strerror.restype = c_char_p
    lib.matcher_strerror.argtypes = [c_int]

    return lib


_LIB: ctypes.CDLL | None = None


def get_library() -> ctypes.CDLL:
    global _LIB
    if _LIB is None:
        _LIB = load_library()
    return _LIB


# ------------------------------------------------------- entrada / saída


class ActorInput(NamedTuple):
    id: int
    tags: list[tuple[int, float]]  # (tag_id, weight)
    type: str = "SOLVER"
    status: str = "ACTIVE"


class DemandInput(NamedTuple):
    id: int
    tags: list[tuple[int, str, float]]  # (tag_id, "REQUIRED"|"DESIRABLE", weight)


class RelationInput(NamedTuple):
    source_tag_id: int
    target_tag_id: int
    type: str  # "RELATED" | "SYNONYM" | "PART_OF"
    weight: float


class DetailOut(NamedTuple):
    demand_tag_id: int
    tag_type: str
    match: str
    actor_tag_id: int | None
    relation_type: str | None
    demand_weight: float
    actor_weight: float
    relation_weight: float
    coverage: float


class MatchOut(NamedTuple):
    actor_id: int
    demand_id: int
    status: str
    score: float
    required_score: float
    desirable_score: float
    match_class: str
    required_count: int
    desirable_count: int
    required_missing_count: int
    algorithm_version: str
    details: list[DetailOut]


class BatchOut(NamedTuple):
    status: str
    evaluated_count: int
    passed_count: int
    results: list[MatchOut]


def _detail_to_py(d: MatchDetail) -> DetailOut:
    relation = RELATION_TYPE_NAME.get(d.relation_type, "NONE")
    return DetailOut(
        demand_tag_id=d.demand_tag_id,
        tag_type="REQUIRED" if d.tag_type == 0 else "DESIRABLE",
        match=MATCH_TYPE_NAME[d.match],
        actor_tag_id=None if d.actor_tag_id == TAG_ID_NONE else d.actor_tag_id,
        relation_type=None if relation == "NONE" else relation,
        demand_weight=d.demand_weight,
        actor_weight=d.actor_weight,
        relation_weight=d.relation_weight,
        coverage=d.coverage,
    )


def run_batch(
    actors: Iterable[ActorInput],
    demand: DemandInput,
    relations: Iterable[RelationInput] = (),
    *,
    desirable_share: float = 0.20,
    threshold: float = 0.0,
    top_k: int = BATCH_TOP_K_UNLIMITED,
    with_details: bool = True,
) -> BatchOut:
    """
    Roda 1 demanda × N atores no motor em C e devolve tudo já em objetos Python.

    Nada de ctypes escapa desta função: a memória do C é copiada para tuplas e
    liberada antes do return, então o chamador não tem o que gerenciar.
    """
    lib = get_library()

    actors = list(actors)
    # Os arrays precisam ficar vivos até batch_match retornar: guardar em locais.
    actor_tag_arrays = []
    c_actors = (Actor * len(actors))() if actors else None
    for i, a in enumerate(actors):
        arr = (ActorTag * len(a.tags))()
        for j, (tag_id, weight) in enumerate(a.tags):
            arr[j].tag_id = tag_id
            arr[j].weight = float(weight)
        actor_tag_arrays.append(arr)
        c_actors[i].id = a.id
        c_actors[i].type = ACTOR_TYPE[a.type]
        c_actors[i].status = ACTOR_STATUS[a.status]
        c_actors[i].tags = ctypes.cast(arr, POINTER(ActorTag)) if a.tags else None
        c_actors[i].tag_count = len(a.tags)

    demand_tag_array = (DemandTag * len(demand.tags))()
    for j, (tag_id, tag_type, weight) in enumerate(demand.tags):
        demand_tag_array[j].tag_id = tag_id
        demand_tag_array[j].type = TAG_TYPE[tag_type]
        demand_tag_array[j].weight = float(weight)
    c_demand = Demand(
        id=demand.id,
        tags=ctypes.cast(demand_tag_array, POINTER(DemandTag)) if demand.tags else None,
        tag_count=len(demand.tags),
    )

    relations = list(relations)
    relation_array = (TagRelationship * len(relations))()
    for j, r in enumerate(relations):
        relation_array[j].source_tag_id = r.source_tag_id
        relation_array[j].target_tag_id = r.target_tag_id
        relation_array[j].type = RELATION_TYPE[r.type]
        relation_array[j].weight = float(r.weight)
    c_relations = RelationSet(
        items=ctypes.cast(relation_array, POINTER(TagRelationship)) if relations else None,
        count=len(relations),
    )

    c_config = MatchConfig(desirable_share=float(desirable_share))
    c_options = BatchOptions(threshold=float(threshold), top_k=int(top_k))
    out = BatchResult()
    failed_actor = c_int64(0)

    err = lib.batch_match(
        ctypes.cast(c_actors, POINTER(Actor)) if actors else None,
        len(actors),
        byref(c_demand),
        byref(c_relations),
        byref(c_config),
        byref(c_options),
        byref(out),
        byref(failed_actor),
    )
    if err != MATCHER_OK:
        # INT64_MIN sinaliza "não é culpa de um ator específico".
        bad = failed_actor.value
        raise MatcherFailure(err, None if bad == -(2**63) else bad)

    try:
        results: list[MatchOut] = []
        for i in range(out.count):
            r = out.results[i]
            details: list[DetailOut] = []
            if with_details and r.details:
                total = r.required_count + r.desirable_count
                details = [_detail_to_py(r.details[k]) for k in range(total)]
            version = r.algorithm_version.decode() if r.algorithm_version else ""
            results.append(
                MatchOut(
                    actor_id=r.actor_id,
                    demand_id=r.demand_id,
                    status=MATCH_STATUS_NAME[r.status],
                    score=r.score,
                    required_score=r.required_score,
                    desirable_score=r.desirable_score,
                    match_class=MATCH_CLASS_NAME[r.match_class],
                    required_count=r.required_count,
                    desirable_count=r.desirable_count,
                    required_missing_count=r.required_missing_count,
                    algorithm_version=version,
                    details=details,
                )
            )
        return BatchOut(
            status=MATCH_STATUS_NAME[out.status],
            evaluated_count=out.evaluated_count,
            passed_count=out.passed_count,
            results=results,
        )
    finally:
        lib.batch_result_free(byref(out))
