"""
Cálculo de hash SHA-256 de arquivos.

O hash é usado como identidade do documento (independente da URL/nome
do arquivo), permitindo detectar duplicidade de conteúdo e servir de
chave de idempotência (hash + parser_version) em etapas futuras.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Lê o arquivo em blocos para não carregar arquivos grandes inteiros
# na memória de uma vez.
_CHUNK_SIZE = 65536


def sha256_of_file(path: Path) -> str:
    """Calcula o SHA-256 de um arquivo e retorna no formato 'sha256:<hex>'."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
