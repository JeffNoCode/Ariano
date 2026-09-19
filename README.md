# ARIANO

Projeto em dois módulos independentes: um **pipeline de extração** que transforma
editais em PDF num JSON estruturado, e um **motor de matching em C** que pontua a
compatibilidade entre atores (empresas, pesquisadores, times) e demandas, a partir
das competências de cada um.

Os dois módulos são desacoplados: o scraper não sabe da existência do motor, e o
motor não lê arquivo, banco nem rede — recebe structs em memória e devolve
resultados. A ligação entre eles (persistência, API, orquestração) ainda não faz
parte deste repositório.

```text
PDF do edital ──▶ scrapper-py ──▶ JSON estruturado ──▶ (camada futura) ──▶ Matching-ariano-c ──▶ ranking de atores
```

## Módulos

| Módulo | Linguagem | O que faz | Documentação |
|---|---|---|---|
| [`scrapper-py/ariano_scraper`](scrapper-py/ariano_scraper) | Python 3.10+ | Valida o PDF, extrai e normaliza o texto, detecta seções, aplica regex (datas, prazos, valores, organização) e reconhece competências conhecidas. Valida o resultado com Pydantic e grava o JSON. | [README do scraper](scrapper-py/ariano_scraper/README.md) |
| [`Matching-ariano-c/matching_engine`](Matching-ariano-c/matching_engine) | C17 (só libc/libm) | Calcula o score de 1 ator × 1 demanda (`matcher_run`) e roda lotes de 1 demanda × N atores (`batch_match`), com threshold, ordenação determinística e top-k. | [README do motor](Matching-ariano-c/matching_engine/README.md) |

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

### Motor de matching (C)

```bash
cd Matching-ariano-c/matching_engine

make            # compila o demo -> build/ariano_demo
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
- **Ainda não existe:** camada de persistência, API, scraping remoto (o
  `pdf/downloader.py` está reservado para essa etapa) e a ponte entre o JSON do
  scraper e as structs do motor.

## Licença

A definir.
