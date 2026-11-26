# API do ARIANO

Versão **1.0.0-rc.1**. A API é servida pelo mesmo processo da interface.
No ambiente local, use a base http://localhost:8000. O Swagger fica em
[`/docs`](http://localhost:8000/docs) e o contrato gerado em
[`/openapi.json`](http://localhost:8000/openapi.json).

## Autenticação e respostas

Faça login em `POST /auth/login` e envie o valor de `access_token` no
cabeçalho `Authorization: Bearer <token>`. A sessão vale 12 horas. O logout
revoga a sessão. O cadastro público cria contas Leitor (`VIEWER`).

| Status | Significado |
|---|---|
| 200, 201, 202, 204 | Consulta ou operação bem-sucedida, criação, tarefa aceita ou resposta sem corpo |
| 401 | Sessão ausente, expirada ou inválida |
| 403 | Perfil sem permissão para a operação |
| 404 | Registro ou tarefa inexistente |
| 409 | Conflito com o estado atual do registro ou tarefa |
| 422 | Dados inválidos ou referência informada inexistente |
| 504 | Tempo limite atingido no processamento do PDF |

Erros de negócio retornam `{"detail": "..."}`. Na validação de parâmetros
e campos do FastAPI, `detail` traz uma lista com a localização e o motivo.

## Rotas

**Sessão** significa qualquer perfil autenticado. **Editor** inclui Editor
e Administrador.

| Método e rota | Acesso | Entrada e resposta de sucesso |
|---|---|---|
| GET `/health` | Público | 200 com estado da API, do banco e do motor |
| POST `/auth/register` | Público | JSON com `name`, `email`, `password` (mínimo 12 caracteres). Retorna 201 e a conta Leitor |
| POST `/auth/login` | Público | JSON com `email` e `password`. Retorna 200 com token, tipo e expiração |
| GET `/auth/me`, POST `/auth/logout` | Sessão | 200 com dados da conta ou confirmação da revogação |
| GET `/stats` | Sessão | 200 com indicadores de documentos, demandas, atores, competências e resultados |
| GET `/users`, PATCH `/users/{user_id}/role` | Administrador | Lista contas ou recebe `{"role":"EDITOR"}`. Retorna 200 |
| GET, POST `/tags` | Sessão para GET, Editor para POST | GET aceita `only_active`. POST recebe `code`, `name` e categorias opcionais e retorna 201 |
| PUT `/tags/relationships` | Editor | IDs de origem e alvo, `relation_type` e `weight` entre 0 e 1. Retorna 200 |
| GET, POST `/actors` | Sessão para GET, Editor para POST | GET aceita `limit` e `offset`. POST recebe tipo, nome, perfil e tags com pesos, retorna 201 |
| GET, PUT, DELETE `/actors/{actor_id}` | Sessão para GET, Editor para PUT e DELETE | Consulta ou atualização retorna 200. Exclusão retorna 204 quando permitida |
| POST `/documents` | Editor | Multipart com campo `file`, PDF de até 10 MB. Retorna 201 com ID, hash, sugestões e indicador de reutilização |
| GET `/documents/{document_id}` | Sessão | 200 com metadados e `payload` da extração |
| GET, POST `/demands` | Sessão para GET, Editor para POST | GET aceita `q`, `status`, `date_from`, `date_to`, `limit` e `offset`. POST cria demanda e retorna 201 |
| GET, PUT `/demands/{demand_id}` | Sessão para GET, Editor para PUT | Consulta ou substituição dos campos da demanda; ambas retornam 200 |
| POST `/demands/{demand_id}/match` | Editor | Opções de matching e persistência. Retorna 200 com a lista calculada |
| GET `/demands/{demand_id}/matches` | Sessão | 200 com resultados gravados. Aceita `limit` e `algorithm_version` |
| GET `/matches/{match_id}/details` | Sessão | 200 com pesos, relação e cobertura por competência |
| GET `/reports/opportunities.csv` | Sessão | Mesmos filtros da lista de oportunidades. Retorna 200 e arquivo CSV em UTF-8 |
| GET `/operations` | Editor | Aceita `limit` e `offset`. Retorna 200 com ações, entidades, usuários e datas |
| GET `/bench/info` | Sessão | 200 com parâmetros aceitos e dados de referência |
| POST `/bench/engine`, POST `/bench/pdfs` | Sessão | Parâmetros do benchmark. Retorna 202 com o ID da tarefa |
| GET `/bench/jobs/{job_id}` | Sessão | 200 com fase, progresso e resultado do benchmark |

## Exemplo de uso

No Swagger, faça login e use **Authorize** com o token retornado. Nos exemplos
abaixo, `TOKEN` é o token da sessão e os IDs devem existir no banco de teste.

```bash
BASE=http://localhost:8000
curl "$BASE/health"
curl -H "Authorization: Bearer $TOKEN" "$BASE/tags?only_active=true"
curl -H "Authorization: Bearer $TOKEN" -F "file=@edital.pdf" "$BASE/documents"
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"Edital de inovação","document_id":1,"tags":[{"tag_id":1,"type":"REQUIRED","weight":1}]}' \
  "$BASE/demands"
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"persist":true,"threshold":0.001,"top_k":10}' "$BASE/demands/1/match"
curl -H "Authorization: Bearer $TOKEN" "$BASE/demands/1/matches"
curl -H "Authorization: Bearer $TOKEN" "$BASE/reports/opportunities.csv?status=OPEN" -o oportunidades.csv
```

A saúde responde `{"status":"ok","database":"ok","engine":"ok"}`. No matching,
`threshold` fica em [0, 1] e `top_k=0` significa sem limite. A opção
`persist=true` salva os resultados da versão do algoritmo. Demanda encerrada
ou cancelada retorna 409 na tentativa de calcular. A leitura dos resultados
salvos continua permitida. As datas dos filtros são inclusivas no fuso de Recife.
