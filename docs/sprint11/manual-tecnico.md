# Manual Técnico

## Arquitetura e tecnologias

A interface em HTML, CSS e JavaScript é servida pela API FastAPI em /app/. A API usa Pydantic para validação, psycopg e psycopg_pool para o PostgreSQL 16 e ctypes para a biblioteca de matching em C17. A extração de editais roda em subprocesso Python com pdfplumber. Docker Compose prepara a API e o banco. O Swagger é gerado pelo FastAPI.

| Componente | Pasta e responsabilidade |
|---|---|
| API | api/ariano_api/ contém rotas, autorização, regras, serviços e repositórios. |
| Interface | api/static/ contém telas, navegação, formulários e consultas HTTP. |
| Banco | api/db/ contém schema, seed e migrações. |
| Parser | scrapper-py/ariano_scraper/ transforma o PDF em dados estruturados e avisos. |
| Motor | Matching-ariano-c/matching_engine/ calcula scores e ordena os resultados. |
| Testes e documentação | api/tests/, api/scripts/ e docs/ registram verificações e instruções. |

## Banco e contratos entre módulos

O sistema usa 15 tabelas. O catálogo usa tags e relações dirigidas. Documentos têm hash único e payload JSONB. Demandas ligam solicitante, documento e competências com tipo e peso. O ranking liga demanda e ator, com uma entrada por versão do algoritmo e detalhes em JSONB. Usuários, sessões e eventos sustentam autenticação, permissões e rastreabilidade.

O fluxo integrado é navegador → API → parser e PostgreSQL → revisão → API → motor C → PostgreSQL → ranking. O motor recebe dados em memória. Para API HTTP, abra /docs e /openapi.json na instância. A referência docs/API.md descreve métodos, Bearer, permissões e exemplos. A API registra o primeiro processamento do PDF e reutiliza o documento pelo hash em envios repetidos.

## Instalação e execução

1. Tenha Git, acesso ao repositório e Docker Engine ou Docker Desktop com Compose v2.
2. Clone o repositório, acesse Ariano/api e suba o perfil full. O build compila a biblioteca C e instala as dependências Python.
3. Crie o administrador local com o segundo comando. Informe a senha quando solicitada.
4. Confira GET /health, abra http://localhost:8000/app/ e faça login. Use http://localhost:8000/docs para testar o contrato.

```bash
docker compose --profile full up -d --build --wait
docker compose --profile full exec api python -m scripts.bootstrap_admin --email admin@ariano.local
```

## Configuração do ambiente

| Variável | Uso |
|---|---|
| DATABASE_URL | Conexão PostgreSQL. No Compose a API usa db:5432 internamente. Em outro ambiente, forneça a conexão por configuração protegida. |
| ARIANO_API_PORT e ARIANO_DB_PORT | Portas locais do host, respectivamente 8000 e 5432 por padrão. A porta do PostgreSQL fica em loopback. |
| ARIANO_AUTO_MIGRATE e ARIANO_SEED_DEMO | Controlam aplicação automática do schema e migrações e preenchimento de demonstração em base vazia. |
| ARIANO_ADMIN_EMAIL e ARIANO_ADMIN_PASSWORD | Criação inicial de administrador por configuração do ambiente. Use senhas próprias, fora do Git. |
| ARIANO_ENGINE_LIB | Caminho da biblioteca C compilada, configurado no Compose. |
| ARIANO_SCRAPER_DIR, ARIANO_SCRAPER_PYTHON e ARIANO_SCRAPER_TIMEOUT | Pasta, intérprete e limite de execução do subprocesso. O limite padrão é 120 segundos. |

O volume ariano_pgdata guarda o banco. A inicialização da API reaplica schema e migrações idempotentes. Preserve o volume nas reinicializações e mantenha backups antes de mudanças em ambientes com dados reais. Para diagnosticar, use docker compose --profile full ps e docker compose --profile full logs --tail=100 api. A instalação externa usa configuração e credenciais próprias.

## Processamento e regras de matching

O parser reconhece campos e competências por regras sobre o texto extraído. A pessoa revisa as sugestões antes de salvar. O ranking é determinístico. Para cada requisito, o motor usa cobertura direta, evidência por relação dirigida ou ausência. As médias ponderadas formam o score, com participação padrão de 20% para as competências desejáveis quando os dois grupos existem. O limiar e o top-k são parametrizáveis. A tela Desempenho compara threads no motor e processos do parser em cargas de teste. OCR permanece fora do escopo atual.

## Manutenção e verificação

Use um banco de teste para executar os roteiros, pois eles criam registros. Execute as suítes da API e do parser com pytest e os testes C com make test-matcher test-parallel. Os testes de ABI requerem GCC ou compilador compatível e os cabeçalhos do motor. Na pasta api/ use python -m scripts.smoke_sprint09 para o fluxo integrado. O README da API ensina a executar a regressão Playwright e a capturar evidências. Para alterações de schema, revise chaves e relacionamentos, versionando novas migrações. As credenciais e os tokens de sessão devem permanecer fora do código e dos logs.
