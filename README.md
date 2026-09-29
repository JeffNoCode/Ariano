# ARIANO

Projeto em três módulos: um **pipeline de extração** que transforma editais em PDF
num JSON estruturado, um **motor de matching em C** que pontua a compatibilidade
entre atores e demandas, e uma **API** que integra os módulos ao PostgreSQL.

O scraper não sabe da existência do motor. O motor não lê arquivo, banco nem rede:
recebe structs em memória e devolve resultados. A API coordena a extração, a
persistência e o cálculo, preservando esse desacoplamento.

```text
PDF do edital ──▶ API ──▶ scrapper-py ──▶ JSON estruturado ──▶ PostgreSQL
                      └──▶ atores + demandas ──▶ Matching-ariano-c ──▶ ranking
```

## Módulos

| Módulo | Linguagem | O que faz | Documentação |
|---|---|---|---|
| [`scrapper-py/ariano_scraper`](scrapper-py/ariano_scraper) | Python 3.10+ | Valida o PDF, extrai e normaliza o texto, detecta seções, aplica regex (datas, prazos, valores, organização) e reconhece competências conhecidas. Valida o resultado com Pydantic e grava o JSON. | [README do scraper](scrapper-py/ariano_scraper/README.md) |
| [`Matching-ariano-c/matching_engine`](Matching-ariano-c/matching_engine) | C17 (só libc/libm) | Calcula o score de 1 ator × 1 demanda (`matcher_run`) e roda lotes de 1 demanda × N atores (`batch_match`), com threshold, ordenação determinística e top-k. | [README do motor](Matching-ariano-c/matching_engine/README.md) |
| [`api`](api) | Python 3.10+, FastAPI, PostgreSQL 16 | Cadastra atores, tags e demandas; guarda documentos e resultados; chama o scraper e o motor C. | [README da API](api/README.md) |

Cada README de módulo detalha seus contratos e limitações. A documentação da
[Sprint 02](docs/sprint02/README.md) reúne arquitetura, protótipo e modelo relacional.

## Como rodar

### Scraper (Python)

```bash
cd scrapper-py/ariano_scraper

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python main.py ./documents/example.pdf --output ./output
pytest                              # suíte de testes
```

O JSON gerado vai para `output/`. As fixtures de teste em `tests/fixtures/`
cobrem PDF com texto nativo, PDF sem camada de texto, PDF corrompido e arquivo
que não é PDF — não é preciso nenhum documento externo para rodar os testes.

### Motor de matching (C)

```bash
cd Matching-ariano-c/matching_engine

make            # compila o demo -> build/ariano_demo
make test       # testes com AddressSanitizer + UBSan + injeção de falha de alocação
make valgrind   # opcional, se valgrind estiver instalado
make shared     # libariano.so; no Windows, mingw32-make shared gera .dll
```

Sem dependências externas: basta um compilador C17 (`gcc` ou `clang`).

### API e banco

Consulte o [guia da API](api/README.md). Em resumo: suba o PostgreSQL com
`docker compose up -d` na pasta `api`, aplique `db/schema.sql` e `db/seed.sql`,
compile a biblioteca compartilhada do motor e execute o FastAPI. O endpoint
`GET /health` verifica banco e motor.

## Estado atual

- **Motor de matching:** funcional. A suíte cobre 57 casos / ~4.800 verificações,
  incluindo ordenação determinística, limites de ponto flutuante, invariância das
  entradas e falha de alocação em todos os pontos, tudo sob ASan/UBSan/LSan.
- **Scraper:** funcional para editais com camada de texto nativa. **OCR ainda não
  está implementado** — PDFs escaneados são identificados e não travam o pipeline,
  mas saem com texto vazio ou parcial e um aviso em `extraction_warnings`.
- **Não usa nenhum serviço pago nem API de LLM.** Toda a extração é regex e
  detecção de seções; todo o matching é aritmética local.
- **API e persistência:** código, DDL, seed e Docker Compose estão no diretório
  `api/`; a execução com banco conectado deve ser verificada no ambiente local.
- **Ainda não existe:** autenticação, interface web integrada e scraping remoto
  (o `pdf/downloader.py` está reservado para essa etapa).

## Licença

A definir.
