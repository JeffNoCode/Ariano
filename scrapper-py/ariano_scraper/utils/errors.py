"""
Exceções do pipeline ARIANO.

Cada exceção carrega o `stage` (etapa) em que ocorreu, para que o
main.py consiga imprimir uma mensagem de erro clara e estruturada em
vez de deixar vazar um traceback bruto para o usuário final.
"""

from __future__ import annotations


class PipelineError(Exception):
    """Erro genérico de uma etapa do pipeline PDF -> JSON."""

    def __init__(self, stage: str, reason: str):
        self.stage = stage
        self.reason = reason
        super().__init__(f"[{stage}] {reason}")


class PdfValidationError(PipelineError):
    """PDF não passou na validação (arquivo, assinatura, páginas, abertura)."""

    def __init__(self, reason: str):
        super().__init__(stage="PDF_VALIDATION", reason=reason)


class PdfExtractionError(PipelineError):
    """Falha ao extrair texto do PDF (arquivo abre, mas extração falha)."""

    def __init__(self, reason: str):
        super().__init__(stage="PDF_EXTRACTION", reason=reason)


class SchemaValidationError(PipelineError):
    """O dicionário produzido pelo parser não passou na validação Pydantic."""

    def __init__(self, reason: str):
        super().__init__(stage="SCHEMA_VALIDATION", reason=reason)
