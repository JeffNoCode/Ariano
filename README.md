# ARIANO

Projeto em três módulos: um **pipeline de extração** que transforma editais em PDF
num JSON estruturado, um **motor de matching em C** que pontua a compatibilidade
entre atores (empresas, pesquisadores, times) e demandas, e uma **API com
persistência em PostgreSQL** que liga os dois e expõe tudo por HTTP.

Os dois primeiros são deliberadamente desacoplados: o scraper não sabe da
existência do motor, e o motor não lê arquivo, banco nem rede — recebe structs em
memória e devolve resultados. A API é a única camada que conhece os dois lados.

```text
PDF do edital ──▶ scrapper-py ──▶ JSON ──▶ PostgreSQL ──▶ Matching-ariano-c ──▶ ranking de atores
                                              └──────── api (FastAPI) ────────┘
```

## Módulos

| Módulo | Linguagem | O que faz | Documentação |
|---|---|---|---|
| [`scrapper-py/ariano_scraper`](scrapper-py/ariano_scraper) | Python 3.10+ | Valida o PDF, extrai e normaliza o texto, detecta seções, aplica regex (datas, prazos, valores, organização) e reconhece competências conhecidas. Valida o resultado com Pydantic e grava o JSON. | [README do scraper](scrapper-py/ariano_scraper/README.md) |
| [`Matching-ariano-c/matching_engine`](Matching-ariano-c/matching_engine) | C17 (só libc/libm) | Calcula o score de 1 ator × 1 demanda (`matcher_run`) e roda lotes de 1 demanda × N atores (`batch_match`), com threshold, ordenação determinística e top-k. | [README do motor](Matching-ariano-c/matching_engine/README.md) |
| [`api`](api) | Python 3.10+ / FastAPI / PostgreSQL | Persiste tags, atores, demandas e documentos; carrega o motor como shared library via ctypes; expõe o ranking por HTTP com Swagger. | [README da API](api/README.md) |

Cada README de módulo tem a documentação completa: fórmula do score, semântica das
relações entre competências, formato do JSON de saída e limitações conhecidas.
Este arquivo é só o mapa.

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

### API (Python + PostgreSQL)

```bash
cd api
docker compose up -d                                    # PostgreSQL local
psql "postgresql://ariano:ariano@localhost:5432/ariano" -f db/schema.sql
pip install -r requirements.txt
uvicorn ariano_api.main:app --reload                    # Swagger em /docs
```

Requer o motor compilado como biblioteca compartilhada
(`make shared` em `Matching-ariano-c/matching_engine`).

### Motor de matching (C)

```bash
cd Matching-ariano-c/matching_engine

make            # compila o demo -> build/ariano_demo
make shared     # compila build/libariano.so (consumida pela API via ctypes)
make test       # testes com AddressSanitizer + UBSan + injeção de falha de alocação
make valgrind   # opcional, se valgrind estiver instalado
```

Sem dependências externas: basta um compilador C17 (`gcc` ou `clang`).

## Estado atual

- **Motor de matching:** funcional. A suíte cobre 57 casos / ~4.800 verificações,
  incluindo ordenação determinística, limites de ponto flutuante, invariância das
  entradas e falha de alocação em todos os pontos, tudo sob ASan/UBSan/LSan.
- **Scraper:** funcional para editais com camada de texto nativa. **OCR ainda não
  está implementado** — PDFs escaneados são identificados e não travam o pipeline,
  mas saem com texto vazio ou parcial e um aviso em `extraction_warnings`.
- **Não usa nenhum serviço pago nem API de LLM.** Toda a extração é regex e
  detecção de seções; todo o matching é aritmética local.
- **API e persistência:** schema PostgreSQL completo, ponte ctypes validada por
  teste de ABI (compara `sizeof`/`offsetof` com o C real) e endpoints cobrindo
  tags, relações, atores, demandas, ingestão de PDF e execução do matching com
  persistência do ranking e da justificativa de cada score.
- **Ainda não existe:** autenticação, migrations versionadas (o `schema.sql` é
  aplicado à mão) e scraping remoto — o `pdf/downloader.py` segue reservado para
  essa etapa.

## Licença

A definir.
