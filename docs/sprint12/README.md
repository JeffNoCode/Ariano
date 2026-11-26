# Sprint 12 — Versão final e Code Freeze

A versão final **v1.0.0** é o ponto congelado para demonstração e entrega.
Use a tag para repetir a instalação descrita no [README](../../README.md).
A API se identifica como 1.0.0 no OpenAPI. A Release Candidate anterior
continua disponível pela tag v1.0.0-rc.1.

## Verificação final

| Verificação | Resultado local |
|---|---|
| Build e inicialização | API, PostgreSQL e motor saudáveis. O build inicial com downloads e compilação levou 4 min 39 s. |
| Banco | PostgreSQL com 15 tabelas. A demanda #5, o documento #1 e dois resultados foram recuperados após reiniciar a API. |
| Regressões | Recálculo vazio, deduplicação e nome de upload, permissões, validação, encerramento e navegação com respostas atrasadas aprovados. |
| API e parser | 33 testes da API com ABI e 61 testes do parser aprovados. |
| Motor C | 4.825 verificações sequenciais e 2.728 paralelas sem falhas sob ASan e UBSan. |
| Demonstração | PDF, revisão, demanda, ranking, filtros, CSV, atores, Histórico e Swagger. A sequência automatizada durou 44,12 s com os serviços já iniciados. |
| Componente avançado | 50 mil atores sintéticos com 1 e 2 threads produziram checksum igual. Quatro editais em cada modo de leitura somaram oito tarefas concluídas. |

Os roteiros HTTP das Sprints 03, 04 e 09 e o smoke da API passaram. O navegador
também executou a regressão Playwright da Sprint 09. Use uma base de teste
para repetir os roteiros, pois eles criam registros.

## Preparação da demonstração

Prepare as imagens e o banco antes da apresentação. Execute
`docker compose --profile full up -d --build --wait` em `api/` e confira
`GET /health`. Se a configuração do banco exigir recriar o contêiner, aguarde
o PostgreSQL saudável antes de reiniciar a API. O ensaio confirmou o mesmo
volume após a retomada.

A sequência é Visão geral → Enviar edital → revisar → salvar → ranking
explicado → filtros e CSV → Histórico → Desempenho. A equipe ainda precisa
repetir essa sequência na máquina de apresentação, definir quem conduz e
conferir o tempo real. Para os vídeos, a demonstração pode usar texto na tela
com narração opcional.

## Materiais

O [planejamento dos vídeos](roteiros-videos.md) contém a demonstração
horizontal de cerca de 5 minutos e a versão vertical de 1 minuto.
As gravações e a edição ficam para a equipe. Consulte também
os [manuais](../sprint11/README.md) e a [referência HTTP](../API.md).
OCR e coleta automática de editais permanecem fora do escopo atual.
