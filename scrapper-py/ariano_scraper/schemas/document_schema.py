from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ExtractionMethod(str, Enum):
    NATIVE_TEXT = "native_text"
    OCR = "ocr"                 
    OCR_REQUIRED = "ocr_required"  


class TrackedValue(BaseModel, Generic[T]):

    model_config = ConfigDict(extra="forbid")

    value: T
    confidence: Confidence
    source_page: int = Field(..., ge=1, description="Página onde a informação foi encontrada (1-based).")


class ProcessingMetadata(BaseModel):

    model_config = ConfigDict(extra="forbid")

    source_url: Optional[str] = None
    source_file: str
    document_hash: str
    processed_at: datetime
    parser_version: str
    extraction_method: ExtractionMethod
    ocr_used: bool = False
    page_count: int = Field(..., ge=0)


class DocumentInfo(BaseModel):

    model_config = ConfigDict(extra="forbid")

    title: Optional[TrackedValue[str]] = None
    organization: Optional[TrackedValue[str]] = None
    publication_date: Optional[TrackedValue[date]] = None
    submission_deadline: Optional[TrackedValue[date]] = None


class Requirement(BaseModel):

    model_config = ConfigDict(extra="forbid")

    text: str
    confidence: Confidence
    source_page: int = Field(..., ge=1)


class Competency(BaseModel):

    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    confidence: Confidence
    source_page: int = Field(..., ge=1)
    matched_text: str = Field(..., description="Trecho exato que casou com a competência (alias encontrado).")


class Financial(BaseModel):

    model_config = ConfigDict(extra="forbid")

    budget: Optional[TrackedValue[float]] = None
    currency: str = "BRL"


class Section(BaseModel):

    model_config = ConfigDict(extra="forbid")

    heading: str
    page: int = Field(..., ge=1)
    text: str


class FinalDocument(BaseModel):

    model_config = ConfigDict(extra="forbid")

    processing_metadata: ProcessingMetadata
    document: DocumentInfo
    requirements: List[Requirement] = Field(default_factory=list)
    competencies: List[Competency] = Field(default_factory=list)
    financial: Financial = Field(default_factory=Financial)
    sections: List[Section] = Field(default_factory=list)
    extraction_warnings: List[str] = Field(default_factory=list)
