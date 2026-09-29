# Sprint 03 - Estrutura inicial funcionando

A Sprint 03 acrescenta autenticação, papéis de acesso, CRUD de atores e uma
interface local integrada à API. A base da Sprint 02 (PostgreSQL, scraper,
motor C e matching) permanece disponível.

## Estrutura implementada

| Componente | Implementação |
|---|---|
| Banco | PostgreSQL 16; migração `api/db/migrations/003_auth.sql` |
| Acesso | Cadastro, login, sessão com token, consulta da conta e logout |
| Perfis | `ADMIN`, `EDITOR`, `VIEWER` |
| CRUD principal | `POST`, `GET`, `PUT` e `DELETE` de atores |
| Interface | `api/static/`, servida pela própria API em `/app/` |
| Deploy local | Docker Compose com banco, API, scraper e biblioteca C compilada na imagem |

O cadastro público cria apenas `VIEWER`. Um administrador pode mudar o papel de
uma conta. `VIEWER` consulta; `EDITOR` cadastra e altera os dados operacionais;
`ADMIN` também gerencia papéis. O tipo de ator (startup, organização, pessoa
solucionadora ou órgão público) não é um papel de acesso.

## Ajuste no modelo de dados

A Sprint 02 tinha 12 tabelas. A migração adiciona `tb_users` (contas, hash de
senha e papel) e `tb_sessions` (hash do token, usuário, validade e revogação).
Um usuário pode ter várias sessões. Não há vínculo obrigatório entre usuário
e ator nesta etapa: contas representam quem acessa o sistema; atores representam
os participantes do ecossistema. A separação evita confundir autorização com
o subtipo de ator. A migração é idempotente e preserva os dados existentes.

## Execução e testes

As instruções de execução, criação do primeiro administrador e comandos de
teste estão no [README da API](../../api/README.md). Os roteiros
[`smoke_sprint03.py`](../../api/scripts/smoke_sprint03.py) e
[`smoke_api.py`](../../api/scripts/smoke_api.py) testam, respectivamente,
acesso/CRUD e a integração com PDF/matching. Ambos trabalham com dados reais
no banco local e geram novos registros de teste.
O [registro da execução local](evidencia-testes.txt) reúne os resultados sem
expor credenciais ou tokens.

## Limites e próximos passos

A interface cobre acesso, perfis e atores; as telas de demandas, documentos e
ranking da Sprint 02 continuam como protótipos. O CRUD de demandas ainda não
inclui edição e exclusão. Antes de disponibilizar a aplicação fora do ambiente
local, são necessários HTTPS, limite de tentativas de login, recuperação de
senha e gestão externa de segredos.

