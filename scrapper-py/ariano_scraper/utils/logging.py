"""
Logging simples e centralizado.

Não usamos nenhuma biblioteca externa aqui: o módulo `logging` da
biblioteca padrão do Python já resolve o que precisamos no MVP
(mensagens claras em stdout/stderr, sem trackback bruto vazando para
o usuário final).
"""

from __future__ import annotations

import logging
import sys


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configura e retorna o logger principal da aplicação ARIANO."""
    logger = logging.getLogger("ariano")

    # Evita duplicar handlers se setup_logging for chamado mais de uma vez
    # (por exemplo, em testes que importam main várias vezes).
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


logger = setup_logging()
