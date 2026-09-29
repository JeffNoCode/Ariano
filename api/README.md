# ARIANO — API e Persistência

Camada que liga as duas metades do projeto: recebe PDFs, guarda tudo em
PostgreSQL e expõe o motor de matching em C por HTTP.

```text
PDF ──subprocesso──▶ scrapper-py ──▶ tb_documents (JSON completo em jsonb)
                                          │
atores + tags + relações ─────────────────┼──ctypes──▶ libariano ──▶ tb_matches
                                          │                         (score_details jsonb)
                                          └──────────▶ GET /demands/{id}/matches
```

## Decisões de arquitetura

**O motor em C entra como shared library, via `ctypes`.** Ele já expõe uma ABI
C limpa (`batch_match`, `batch_result_free`), então virar `.so`/`.dll` custou uma
regra no Makefile e nenhum código novo em C. A alternativa — uma CLI trocando
JSON — exigiria escrever um parser JSON em C à mão, já que o motor não tem
nenhuma dependência externa, e isso é código novo justamente na parte mais
testada do projeto.

O preço dessa escolha é que `engine/bindings.py` declara os structs à mão e
precisa ficar em sincronia com `domain.h`. Um campo novo no C sem o campo
correspondente aqui não dá erro: dá score plausível e errado, que é o pior
tipo de bug. Por isso existe `tests/test_abi.py`, que compila um programa C
comparando `sizeof` e `offsetof` de cada campo com o que o `ctypes` acha.
**Rode esse teste sempre que mexer nos headers.**

**O scraper, ao contrário, entra por subprocesso.** Ele já é uma CLI, seus
imports de topo (`parser`, `pdf`, `utils`) só resolvem com o cwd na pasta dele,
e PDF malformado é a maior fonte de travamento do pipeline. Num processo
separado, o pior caso é um timeout — não a API inteira caindo.

**Os pesos são validados em três camadas** (Pydantic, CHECK do banco, motor).
Redundante de propósito: o cliente recebe 422 com o campo exato antes de gastar
banco, e o banco impede que dado ruim chegue ao motor, que reage a dado
inválido derrubando o lote inteiro (falha rápida).

## Subindo

```bash
# 1. compile o motor como biblioteca compartilhada (Linux: .so; Windows: .dll)
cd ../Matching-ariano-c/matching_engine && make shared && cd -

# 2. banco
docker compose up -d
psql "postgresql://ariano:ariano@localhost:5432/ariano" -f db/schema.sql
psql "postgresql://ariano:ariano@localhost:5432/ariano" -f db/seed.sql   # opcional

# 3. API
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn ariano_api.main:app --reload
```

Swagger em <http://localhost:8000/docs>. Checagem rápida de que banco e motor
subiram: `curl localhost:8000/health`.

No Windows, use `mingw32-make shared` no diretório do motor. O compilador deve
gerar uma DLL da mesma arquitetura do Python que executa a API (64 bits para
Python 64 bits); uma DLL de 32 bits não pode ser carregada por esse processo.
O caminho pode ser ajustado por `ARIANO_ENGINE_LIB` no `.env`.

## Verificando que a integração funciona

Com o `seed.sql` aplicado:

```bash
curl -X POST localhost:8000/demands/1/match -H 'Content-Type: application/json' -d '{}'
```

O cenário do seed é construído para exercitar os três caminhos do motor, e os
scores são previsíveis — se saírem estes números, a ponte Python ↔ C está
correta de ponta a ponta:

| Ator | Score | Classe | Por quê |
|---|---|---|---|
| Laboratório Alpha | **0.912** | `EXACT` | Tem as duas REQUIRED (1.0 e 0.9) e ainda a DESIRABLE (0.8) |
| Startup Beta | **0.64** | `RELATED` | Não tem NLP, mas tem LLM, e `LLM → NLP` (peso 0.9) cobre; sem DESIRABLE |
| Construtora Gama | — | — | Não aparece: nenhuma tag capaz de pontuar (use `evaluate_all_actors: true` para vê-la com score 0) |

Passe `{"persist": true}` para gravar o ranking, e depois
`GET /demands/1/matches` e `GET /matches/{id}/details` para ver o resultado
gravado e a explicação tag a tag de cada score.

## Endpoints

| Método | Rota | O que faz |
|---|---|---|
| `GET` | `/health` | Banco e motor respondendo |
| `POST` `GET` | `/tags` | Cadastro de competências |
| `PUT` | `/tags/relationships` | Relação direcionada `source → target` |
| `POST` `GET` | `/actors`, `/actors/{id}` | Atores com suas competências e pesos |
| `POST` `GET` | `/demands`, `/demands/{id}` | Demandas com tags REQUIRED/DESIRABLE |
| `POST` | `/demands/{id}/match` | **Roda o motor**: threshold, top-k, `desirable_share`, `persist` |
| `GET` | `/demands/{id}/matches` | Ranking já gravado |
| `GET` | `/matches/{id}/details` | Explicação do score, tag a tag |
| `POST` | `/documents` | Upload de PDF → scraper → `tb_documents` |
| `GET` | `/documents/{id}` | JSON completo do documento |

## Modelo de dados

| Tabela | Papel |
|---|---|
| `tb_actors` | Dados comuns a todo ator (nome, status, cidade, documento) + `actor_type` |
| `tb_solvers` / `tb_startups` / `tb_organizations` / `tb_government_agencies` | Um por `actor_type`, 1:1 com `tb_actors` via `actor_id`. Triggers garantem que a linha do subtipo bate com o `actor_type` declarado — não dá para cadastrar um SOLVER com linha em `tb_startups` |
| `tb_tags`, `tb_tag_relationships` | Vocabulário de competências e o grafo direcionado entre elas. `relation_type` faz parte da chave: um mesmo par de tags pode ter RELATED *e* SYNONYM simultaneamente |
| `tb_actor_tags` | Quem tem competências, e com que força (peso em [0,1]) |
| `tb_documents` | Um registro por PDF processado; `payload` jsonb guarda o JSON inteiro do scraper, hash único evita reprocessar. **Fora do ERD do time** — ver nota no topo de `schema.sql` |
| `tb_demands`, `tb_demand_tags` | O que se pede (com `requester_id` apontando para o ator solicitante), tipo por tag (REQUIRED/DESIRABLE) e importância (peso > 0) |
| `tb_matches` | Uma linha por (demanda, ator, versão do algoritmo). `score_details` guarda em **jsonb** tudo que o motor calculou além do score bruto — inclusive o detalhe por tag, que antes vivia numa tabela separada |

`algorithm_version` faz parte da chave única de `tb_matches`: rodar de novo com
uma versão nova do motor não apaga o histórico da anterior, o que permite
comparar mvp-1 com mvp-2 na mesma base.

**`score_details` é jsonb, não uma tabela separada.** Isso segue o ERD do
time à risca, mas troca consulta SQL por operadores jsonb — dá pra fazer
`score_details @> '{"status":"EVALUATED"}'` ou `jsonb_array_elements
(score_details->'details')`, com um índice GIN já criado em
`ix_matches_details_gin`. Se "quantos matches cobriram a tag X via RELATED"
virar consulta frequente, vale reavaliar.

## Testes

```bash
pytest                  # inclui o teste de ABI (precisa de um compilador C)
```

## Schema alinhado ao ERD do time

`db/schema.sql` segue o diagrama que o time desenhou: atores por subtipo
(`tb_solvers`/`tb_startups`/`tb_organizations`/`tb_government_agencies`, 1:1
com `tb_actors`), `tb_matches` com `score_details` em jsonb, e
`tb_tag_relationships` com `relation_type` na chave primária. Três pontos
saem do diagrama de propósito, comentados no topo do arquivo e resumidos
aqui:

- **`tb_documents` foi mantida** mesmo não estando no ERD — sem ela o
  `POST /documents` não teria onde gravar o JSON do scraper. Linkada só por
  `tb_demands.document_id`, nullable; dá pra remover sem afetar o resto se o
  time decidir que documento é só um anexo solto.
- **`tb_demands.budget/deadline/currency` foram mantidas** — não estão no
  ERD, mas são dados reais de edital que a API já expunha.
- **`tb_matches.algorithm_version` foi mantida** — não está no ERD, mas sem
  ela rodar o motor numa versão nova apagaria o histórico da anterior.

## O que ainda falta

- **Autenticação.** Não há nenhuma. Não exponha esta API na internet como está.
- **Migrations.** `schema.sql` é aplicado à mão; com o projeto andando, vale
  trocar por Alembic antes da primeira mudança de schema em produção.
- **Criar demanda a partir de documento automaticamente.** Hoje o `POST
  /documents` guarda o JSON e devolve as competências reconhecidas, mas quem
  monta a demanda com pesos é uma chamada separada a `POST /demands` — de
  propósito, porque escolher peso e REQUIRED vs DESIRABLE é decisão humana.
- **Paginação nos rankings** e cache de relações, se a base crescer.
