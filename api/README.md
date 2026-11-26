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

### API completa no Docker

Na pasta `api`, execute:

```bash
docker compose --profile full up -d --build --wait
docker compose --profile full exec api python -m scripts.bootstrap_admin --email admin@ariano.local
```

O último comando pede uma senha de no mínimo 12 caracteres. Abra a interface
em <http://localhost:8000/app/> com essa conta; a documentação da API está em
<http://localhost:8000/docs>. O cadastro público cria apenas contas `VIEWER`.
Um administrador pode promover contas a `EDITOR` ou `ADMIN` na tela Usuários.

Em um volume novo, o PostgreSQL aplica os scripts de inicialização do Compose.
Ao subir, a API aplica o schema e as migrações idempotentes, inclusive em um
volume existente. Os dados anteriores permanecem no volume `ariano_pgdata`.
Defina `ARIANO_API_PORT` ou `ARIANO_DB_PORT` para alterar as portas do host.
A aplicação continua acessando o PostgreSQL pelo endereço interno `db:5432`.

O [guia HTTP](../docs/API.md) lista rotas, papéis, parâmetros, respostas e
exemplos. O arquivo gerado pela própria aplicação está em `/openapi.json`.

Para repetir os testes em PowerShell, defina o e-mail da conta administrativa.
Cada roteiro pedirá a senha sem exibi-la na tela:

```powershell
$env:ARIANO_TEST_ADMIN_EMAIL = 'admin@ariano.local'
py scripts/smoke_sprint03.py
py scripts/smoke_api.py
Remove-Item Env:ARIANO_TEST_ADMIN_EMAIL
```

O primeiro roteiro valida cadastro, login, perfis, CRUD de atores, logout e
respostas 401/403/404. O segundo valida PDF, demanda, motor C e ranking. Ambos
criam dados de teste com identificadores únicos.

Para a Sprint 04, a tela **Oportunidades** integra PDF, revisão, demanda e
ranking salvo. Execute `powershell -ExecutionPolicy Bypass -File
scripts/run_sprint04_evidence.ps1` na pasta `api`: o roteiro testa o fluxo,
reinicia a API e confirma que documento, demanda e ranking permanecem no banco.
O resultado fica em `docs/sprint04/evidencia-testes.txt`.

Para inspecionar uma falha:

```bash
docker compose --profile full ps
docker compose --profile full logs --tail=100 api
```

O Docker compila uma `libariano.so` Linux com a mesma arquitetura da imagem
Python. Isso evita o conflito entre a DLL Windows de 32 bits e o Python local
de 64 bits.

### Execução local sem Docker para a API

```bash
# 1. compile o motor como biblioteca compartilhada (Linux: .so; Windows: .dll)
cd ../Matching-ariano-c/matching_engine && make shared && cd -

# 2. banco
docker compose up -d
psql "postgresql://ariano:ariano@localhost:5432/ariano" -f db/schema.sql
psql "postgresql://ariano:ariano@localhost:5432/ariano" -f db/seed.sql   # opcional
psql "postgresql://ariano:ariano@localhost:5432/ariano" -f db/migrations/003_auth.sql

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

Com o `seed.sql` aplicado e um token obtido em `POST /auth/login`:

```bash
curl -X POST localhost:8000/demands/1/match -H 'Content-Type: application/json' -H 'Authorization: Bearer SEU_TOKEN' -d '{}'
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
| `POST` | `/auth/register`, `/auth/login`, `/auth/logout` | Cadastro, entrada e encerramento de sessão |
| `GET` | `/auth/me` | Conta autenticada |
| `GET` `PATCH` | `/users`, `/users/{id}/role` | Consulta e alteração de papéis pelo administrador |
| `POST` `GET` | `/tags` | Cadastro de competências |
| `PUT` | `/tags/relationships` | Relação direcionada `source → target` |
| `POST` `GET` `PUT` `DELETE` | `/actors`, `/actors/{id}` | CRUD de atores com suas competências e pesos |
| `POST` `GET` | `/demands`, `/demands/{id}` | Cadastro, listagem e consulta de demandas com tags REQUIRED/DESIRABLE |
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
| `tb_users`, `tb_sessions` | Contas com papéis ADMIN/EDITOR/VIEWER e sessões de acesso com token armazenado como hash; criadas pela migração da Sprint 03 |

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

- **Produção.** O login e os perfis são uma base local. Antes de expor o
  serviço à internet, faltam HTTPS, limite de tentativas de login, política
  de recuperação de senha, gestão de segredos e migrações automatizadas.
- **Decisão humana após a extração.** A interface já preenche uma nova demanda
  a partir do PDF, mas a pessoa revisa os campos e define pesos e tipo de cada
  competência antes de salvar. O scraper não decide essas regras sozinho.
- **Paginação nos rankings** e cache de relações, se a base crescer.

## Relatório de oportunidades e histórico

Em **Oportunidades**, a busca por título ou solicitante pode ser combinada com
a situação e o período de criação (datas inclusivas no fuso de Recife). A lista
é paginada e **Exportar CSV** baixa todos os registros da mesma seleção, em
UTF-8 com separador ponto e vírgula. A planilha inclui contagem de competências,
quantidade de resultados gravados e melhor score por demanda.

**Histórico** exibe as 100 operações mais recentes para editores e administradores.
A API registra cadastro, atualização e exclusão de atores, criação de demandas,
primeiro processamento de cada documento e cálculos de ranking com persistência.
A migração `005_operation_log.sql` é aplicada na inicialização padrão da API e
passa a registrar operações a partir desse momento. O evento é gravado na mesma
transação da operação correspondente.

As rotas de consulta são `GET /demands`, `GET /reports/opportunities.csv` e
`GET /operations`. A consulta de oportunidades e o CSV aceitam `q`, `status`,
`date_from` e `date_to`.

## Edição de oportunidades e permissões

Editores e administradores podem editar uma oportunidade pelo detalhe ou via
`PUT /demands/{id}`, inclusive para encerrar, cancelar ou reabrir a demanda.
O ranking salvo permanece disponível para consulta após o encerramento.
Um novo cálculo exige uma oportunidade aberta ou em análise.

A edição de competências, pesos ou prioridades invalida o ranking antigo.
Recalcular sem candidatos elegíveis remove os resultados da versão atual.
A consulta de ranking usa a versão atual por padrão e aceita o parâmetro
`algorithm_version` para recuperar resultados de outra versão ainda gravada.
O desempate usa score, quantidade de obrigatórias ausentes e ID do ator.

O cadastro público cria contas Leitor. Editores podem atualizar dados e
consultar o histórico. A gestão de papéis é exclusiva de administradores,
registra alterações no histórico e protege a última conta administradora ativa.


## Verificação integrada

Use um banco de teste. Os roteiros criam registros no ambiente informado.
Suba a API e configure `ARIANO_TEST_URL` e `ARIANO_TEST_ADMIN_EMAIL`. Os
roteiros Python solicitam a senha quando `ARIANO_TEST_ADMIN_PASSWORD` não
está definida. Na pasta `api/`:

```bash
python -m pytest -q tests
python -m scripts.smoke_sprint09
```

A suíte de ABI requer GCC ou outro compilador C compatível e os cabeçalhos
do motor no checkout. O teste HTTP verifica gravação do ranking, encerramento,
bloqueio de recálculo, listagem filtrada, CSV equivalente e histórico.

Para a regressão de navegação, instale Playwright como dependência apenas
do ambiente de teste. Na raiz do repositório:

```bash
npm install --prefix api/tests/browser --no-save --no-package-lock playwright
node api/tests/browser/node_modules/playwright/cli.js install chromium
node api/tests/browser/sprint09.cjs
```

Defina as mesmas variáveis de API, incluindo `ARIANO_TEST_ADMIN_PASSWORD`.
O teste valida login, mensagem do formulário, abertura de demandas com
respostas fora de ordem, retorno à lista, ranking salvo, navegação em 420 px,
histórico e logout. Defina `ARIANO_TEST_EVIDENCE_DIR` para gravar as capturas.
