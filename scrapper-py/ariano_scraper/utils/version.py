"""
Versão central do parser.

Toda vez que a lógica de extração/parsing mudar de forma relevante
(novos padrões de regex, nova estratégia de seções, etc.), incremente
esse valor. Ele é gravado em `processing_metadata.parser_version` no
JSON de saída, permitindo saber, no futuro, com qual lógica cada
documento foi processado.

Não espalhe strings de versão pelo resto do código: importe esta
constante.
"""

PARSER_VERSION = "1.0.0"
