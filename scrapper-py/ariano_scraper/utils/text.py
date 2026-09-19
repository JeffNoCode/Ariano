"""Pequenos helpers de texto usados na detecção de seções/heurísticas."""

from __future__ import annotations

import unicodedata


def strip_accents(text: str) -> str:
    """Remove acentuação de uma string, apenas para fins de COMPARAÇÃO
    (nunca usar o resultado como valor a ser persistido)."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))
