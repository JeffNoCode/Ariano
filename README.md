# ARIANO

**Release Candidate:** [v1.0.0-rc.1](https://github.com/JeffNoCode/Ariano/tree/v1.0.0-rc.1)

> **Novo no projeto?** Comece pelo [COMO_FUNCIONA.md](COMO_FUNCIONA.md), o passo a
> passo do fluxo completo. Para publicar online, veja [docs/DEPLOY.md](docs/DEPLOY.md).
> Paralelismo (threads no motor em C, processos no scraper) e a página
> **Desempenho**: [docs/PARALELISMO.md](docs/PARALELISMO.md).

Projeto em três módulos: um **pipeline de extração** que transforma editais em PDF
num JSON estruturado, um **motor de matching em C** que pontua a compatibilidade
entre atores e demandas, e uma **API** que integra os módulos ao PostgreSQL.

O objetivo é reduzir a triagem manual de editais e explicar a compatibilidade
entre oportunidades de inovação e as competências cadastradas pelos atores.

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
| [`Matching-ariano-c/matching_engine`](Matching-ariano-c/matching_engine) | C17 (só libc/libm) | Calcula o score de 1 ator × 1 demanda (`matcher_run`) e roda lotes de 1 demanda × N atores (`batch_match`), com threshold, ordenação determinística e top-k. A versão `batch_match_parallel` faz o mesmo lote dividido entre N threads (pthreads), com resultado idêntico. | [README do motor](Matching-ariano-c/matching_engine/README.md) |
| [`api`](api) | Python 3.10+, FastAPI, PostgreSQL 16 | Integra banco, scraper e motor C; oferece cadastro, login, perfis, CRUD de atores e interface web local. | [README da API](api/README.md) |

Cada README de módulo detalha seus contratos e limitações. A documentação da
[Sprint 02](docs/sprint02/README.md) reúne arquitetura, protótipo e modelo relacional.
A [Sprint 03](docs/sprint03/README.md) descreve a base funcional, a migração de
usuários e sessões, os testes e as instruções de demonstração local.

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
make test       # suíte original + paralelo (ASan/UBSan, falha de alocação) + ThreadSanitizer
make bench      # tempo com 1, 2, 4 e 8 threads (200 mil atores sintéticos)
make valgrind   # opcional, se valgrind estiver instalado
make shared     # libariano.so; no Windows, mingw32-make shared gera .dll
```

Sem dependências externas: basta um compilador C17 (`gcc` ou `clang`).

### API, interface e banco com Docker

Pré-requisitos: Git, Docker Engine ou Docker Desktop com Docker Compose v2
e acesso ao repositório. O build instala as dependências Python, compila o
motor C17 e usa PostgreSQL 16. A interface é servida pela própria API.

```bash
git clone https://github.com/JeffNoCode/Ariano.git
cd Ariano
git checkout v1.0.0-rc.1
cd api
docker compose --profile full up -d --build --wait
docker compose --profile full exec api python -m scripts.bootstrap_admin --email admin@ariano.local
```

O comando de criação da conta solicita uma senha de pelo menos 12 caracteres.
Abra a [interface local](http://localhost:8000/app/), o
[Swagger](http://localhost:8000/docs) ou o [schema OpenAPI](http://localhost:8000/openapi.json).

O Compose usa o serviço `db` e guarda o PostgreSQL no volume `ariano_pgdata`.
A API aplica o schema e as migrações idempotentes na inicialização. Para mudar
as portas no host, defina `ARIANO_API_PORT` (8000) e `ARIANO_DB_PORT` (5432)
antes de subir. O PostgreSQL é publicado apenas em loopback no host, e a API
se conecta internamente a `db:5432`. Em instalação fora do Compose, configure
`DATABASE_URL` com a conexão PostgreSQL do ambiente.

Consulte a [referência HTTP](docs/API.md), o [guia da API](api/README.md)
e o [registro da Release Candidate](docs/sprint10/README.md).

### Online

Render (container) + Neon (PostgreSQL), com `render.yaml` na raiz. O administrador
é criado pelas variáveis `ARIANO_ADMIN_EMAIL`/`ARIANO_ADMIN_PASSWORD` e o banco
vazio recebe uma demonstração fictícia. Passo a passo em [docs/DEPLOY.md](docs/DEPLOY.md).

## Paralelismo

O ARIANO executa trabalho em paralelo em dois pontos, e a página **Desempenho**
do site compara, ao vivo e com barras de progresso, o tempo sequencial com o paralelo.

| Onde | Tipo | Como |
|---|---|---|
| Motor de matching (C) | **Threads** (memória compartilhada) | `batch_match_parallel()` divide os atores em blocos, um por pthread; cada thread avalia, filtra, ordena e corta no top-k a sua parte, e a thread principal intercala as listas |
| Leitura de editais | **Processos** (memória separada) | Cada PDF é lido por um processo próprio do scraper; vários editais ao mesmo tempo (o GIL do Python impediria ganho com threads) |

**Mesmo resultado, sempre:** a ordem do ranking é total e determinística, então o
paralelo devolve exatamente o mesmo ranking do sequencial. Isso é verificado por
2.728 comparações em `tests/test_parallel.c` (ASan/UBSan), pelo ThreadSanitizer
(nenhuma condição de corrida) e pelo checksum mostrado na página Desempenho.

**Lei de Amdahl na prática:** a primeira versão ordenava o resultado inteiro numa
thread só e ganhava apenas 1,4× com 4 threads. Levar a ordenação para dentro de
cada thread reduziu a parte sequencial à intercalação e o ganho subiu para ~3×.

| Medido em 26/11/2026 (Docker Desktop, 8 CPUs) | Sequencial | Paralelo | Ganho |
|---|---|---|---|
| Motor, 200 mil atores × 9 rodadas, 8 threads | 2,27 s | 0,60 s | **3,8×** |
| 4 editais, 2 ao mesmo tempo | 6,31 s | 3,91 s | **1,6×** |

> No plano gratuito do Render o servidor tem só uma fração de 1 CPU, então o ganho
> online é pequeno; por isso a página também mostra a medição de referência acima.

Implementação, endpoints `/bench/*` e como medir de novo:
[docs/PARALELISMO.md](docs/PARALELISMO.md).

## Estado atual

- **Motor de matching:** funcional. A suíte cobre 57 casos / ~4.800 verificações,
  incluindo ordenação determinística, limites de ponto flutuante, invariância das
  entradas e falha de alocação em todos os pontos, tudo sob ASan/UBSan/LSan.
  A versão paralela tem mais 2.728 verificações de equivalência e roda limpa
  sob ThreadSanitizer.
- **Scraper:** funcional para editais com camada de texto nativa. **OCR ainda não
  está implementado** — PDFs escaneados são identificados e não travam o pipeline,
  mas saem com texto vazio ou parcial e um aviso em `extraction_warnings`.
- **Não usa nenhum serviço pago nem API de LLM.** Toda a extração é regex e
  detecção de seções; todo o matching é aritmética local.
- **API e persistência:** integra autenticação, operações de atores, ingestão de
  editais, ciclo de vida de demandas e ranking versionado. PostgreSQL guarda
  também o histórico de operações.
- **Interface web:** Visão geral, Oportunidades com busca, filtros e CSV, Atores,
  Histórico, Desempenho e gestão de usuários, servidos pela API em `/app/`.
- **Verificação:** o [guia da API](api/README.md#verificação-integrada) descreve
  os testes de API, ABI e navegação, incluindo os roteiros da Sprint 09.
- **Ainda não existe:** scraping remoto (`pdf/downloader.py` está reservado
  para essa etapa). A autenticação local ainda precisa de reforços para produção.

## Manuais e documentação consolidada

- [Manual do Usuário](docs/sprint11/manual-usuario.md)
- [Manual Técnico](docs/sprint11/manual-tecnico.md)
- [Documentação consolidada](docs/sprint11/documentacao-consolidada.md)
- [Registro de revisão da Sprint 11](docs/sprint11/README.md)

## Estrutura do repositório

- `api/ariano_api/` contém a API FastAPI e a integração com o motor.
- `api/static/` contém a interface web em HTML, CSS e JavaScript.
- `api/db/` contém o schema, dados iniciais e migrações do PostgreSQL.
- `scrapper-py/` contém o parser de editais e seus testes.
- `Matching-ariano-c/` contém a biblioteca C17 e suas suítes.
- `docs/` contém guias de execução, API e evidências do projeto.

## Equipe

| Integrante | Matrícula | Função |
|---|---|---|
| André Gomes dos Santos Filho | 01586077 | Desenvolvimento |
| Guilherme Andrade de Aguiar | 01606498 | Desenvolvimento |
| Jefferson de Souza Santo | 01608589 | Desenvolvimento |
| Matheus Augusto de Moura | 01586638 | Desenvolvimento |
| Raul Anthony de Sousa Muniz | 01633454 | Scrum Master e desenvolvimento |

## Licença

A definir.

