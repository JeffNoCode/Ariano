
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ActorTypeName = Literal["SOLVER", "STARTUP", "ORGANIZATION", "GOVERNMENT_AGENCY"]
ActorStatusName = Literal["ACTIVE", "INACTIVE", "SUSPENDED"]
DocumentTypeName = Literal["CPF", "CNPJ"]
TagTypeName = Literal["REQUIRED", "DESIRABLE"]
RelationTypeName = Literal["RELATED", "SYNONYM", "PART_OF"]
DemandStatusName = Literal["OPEN", "EVALUATING", "CLOSED", "CANCELLED"]
MaturityLevelName = Literal["IDEATION", "MVP", "GROWTH", "SCALE"]
UserRoleName = Literal["ADMIN", "EDITOR", "VIEWER"]


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=12, max_length=128)


class LoginIn(BaseModel):
    email: str
    password: str


class RoleUpdateIn(BaseModel):
    role: UserRoleName


class TagIn(BaseModel):
    code: str = Field(max_length=63, examples=["MACHINE_LEARNING"])
    name: str = Field(examples=["Machine Learning"])
    category: str | None = None
    subcategory: str | None = None


class TagOut(BaseModel):
    id: int
    code: str
    name: str
    category: str | None
    subcategory: str | None
    is_active: bool


class RelationIn(BaseModel):
    """
    Direcionada: possuir `source` é evidência de compatibilidade com `target`.
    A inversa NÃO é criada automaticamente, nem para SYNONYM — se a
    equivalência vale nos dois sentidos, cadastre as duas linhas.
    """

    source_tag_id: int
    target_tag_id: int
    relation_type: RelationTypeName = "RELATED"
    weight: float = Field(ge=0, le=1, examples=[0.8])


class ActorTagIn(BaseModel):
    tag_id: int
    weight: float = Field(ge=0, le=1, description="Força da competência. 0 = sem evidência.")


class ActorProfile(BaseModel):
    """
    Campos específicos do subtipo. Preencha só os que correspondem a `type`;
    os demais são ignorados. Ver tb_solvers/tb_startups/tb_organizations/
    tb_government_agencies no schema.
    """

    bio: str | None = None  # SOLVER
    sector: str | None = None  # STARTUP
    solution_description: str | None = None  # STARTUP
    maturity_level: MaturityLevelName | None = None  # STARTUP
    business_sector: str | None = None  # ORGANIZATION
    agency_type: str | None = None  # GOVERNMENT_AGENCY


class ActorIn(BaseModel):
    type: ActorTypeName
    name: str
    description: str | None = None
    document: str | None = None
    document_type: DocumentTypeName | None = None
    status: ActorStatusName = "ACTIVE"
    city: str | None = None
    state: str | None = Field(default=None, min_length=2, max_length=2)
    profile: ActorProfile = ActorProfile()
    tags: list[ActorTagIn] = []

    @model_validator(mode="after")
    def _document_needs_type(self) -> "ActorIn":
        if self.document and not self.document_type:
            raise ValueError("document_type é obrigatório quando document é informado")
        return self


class DemandTagIn(BaseModel):
    tag_id: int
    type: TagTypeName = "REQUIRED"
    weight: float = Field(gt=0, description="Importância relativa. Precisa ser > 0.")


class DemandIn(BaseModel):
    requester_id: int | None = None
    title: str = Field(min_length=3, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    status: DemandStatusName = "OPEN"
    deadline: date | None = None
    budget: float | None = Field(default=None, ge=0)
    currency: str = Field(default="BRL", min_length=3, max_length=3)
    document_id: int | None = None
    tags: list[DemandTagIn] = Field(min_length=1)

    @model_validator(mode="after")
    def _valid_demand(self) -> "DemandIn":
        if len(self.title.strip()) < 3:
            raise ValueError("o título da demanda deve ter pelo menos 3 caracteres")
        ids = [tag.tag_id for tag in self.tags]
        if len(ids) != len(set(ids)):
            raise ValueError("uma competência não pode aparecer duas vezes na demanda")
        self.title = self.title.strip()
        return self


class MatchOptions(BaseModel):
    threshold: float = Field(default=0.0, ge=0, le=1)
    top_k: int = Field(default=0, ge=0, description="0 = sem limite.")
    desirable_share: float = Field(default=0.20, ge=0, le=1)
    only_active: bool = True
    evaluate_all_actors: bool = Field(
        default=False,
        description=(
            "Por padrão só são avaliados atores que possuem alguma tag capaz de "
            "pontuar nesta demanda. True avalia toda a base, incluindo quem "
            "obtém score 0."
        ),
    )
    persist: bool = Field(default=False, description="Gravar o ranking em tb_matches.")

