# Sprint 10 — Release Candidate

A versão candidata **v1.0.0-rc.1** reúne a interface web, a API FastAPI,
o PostgreSQL, o parser de editais e o motor de ranking em C. A versão
`1.0.0-rc.1` também é informada em `/openapi.json`.

## Verificação da candidata

| Verificação | Resultado local |
|---|---|
| Inicialização em banco novo | API e PostgreSQL saudáveis, motor carregado |
| Banco | PostgreSQL 16.15, 15 tabelas, 15 PKs, 16 FKs, 16 CHECKs e 3 restrições UNIQUE em `pg_constraint`, todas validadas |
| Integração | Roteiros das Sprints 03, 04 e 09 e smoke da API aprovados |
| Navegador | Login, validação, regressão de navegação, PDF → revisão → demanda → ranking, histórico e logout |
| Interface | Limpeza dos filtros verificada em 420 px, sem rolagem horizontal, e navegação com item atual identificado |
| Persistência | Documento, demanda, competências e três resultados recuperados após reiniciar a API |
| Contrato HTTP | Swagger renderizado, OpenAPI com versão da RC e 31 operações |
| Suítes | 31 testes Python da API, incluindo ABI, e 61 do parser aprovados. Motor C com 4.825 verificações sequenciais e 2.728 paralelas, sem falhas sob ASan/UBSan |

O schema é definido em [schema.sql](../../api/db/schema.sql). Em inicialização
normal, a API aplica esse arquivo e as [migrações](../../api/db/migrations/)
em ordem. As migrações incluem autenticação, catálogo do parser e histórico.
O teste subiu a aplicação no Docker e reiniciou a API com o mesmo volume.

## Execução e demonstração

1. Selecione a tag `v1.0.0-rc.1` e siga o [README principal](../../README.md).
2. Abra a interface em `/app/` e acompanhe `GET /health`.
3. Envie um PDF com texto, revise o cadastro e calcule o ranking.
4. Reabra a demanda e confira documento, resultado e explicação por competência.
5. Combine filtros em Oportunidades, exporte CSV e confira o Histórico com perfil habilitado.
6. Use o [guia HTTP](../API.md) e o Swagger em `/docs` para demonstrar o contrato.

A validação cobriu a execução local com Docker e Chromium. A configuração
do ambiente de apresentação e a verificação da implantação externa ficam
para o ensaio final. OCR permanece fora do escopo da candidata.
