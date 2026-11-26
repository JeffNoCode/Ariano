# Como o ARIANO funciona

> **ARIANO** — ARquitetura de Inteligência Artificial Naturalmente Ordenada.
> Motor de recomendação que conecta **demandas de inovação** (editais, desafios
> públicos, dores de empresas) a **atores com as competências certas** (startups,
> profissionais, organizações e órgãos públicos), e explica por que cada
> recomendação faz sentido.

Este documento é o passo a passo para quem está chegando no projeto. Para os
detalhes de cada módulo, siga os links ao final.

---

## 1. O problema

Hoje, achar quem pode resolver uma demanda depende de alguém ler editais à mão e
"lembrar" quem sabe o quê. Isso é lento, não escala e não deixa rastro de **por
que** um parceiro foi escolhido.

O ARIANO resolve isso em três ideias:

1. **Um vocabulário comum de competências** (tags como `MACHINE_LEARNING`,
   `WHATSAPP`, `IOT`), com relações entre elas ("quem sabe LLM tem evidência de NLP").
2. **Um cálculo determinístico e auditável**: o mesmo dado de entrada gera sempre
   o mesmo ranking, e cada score vem com a explicação competência por competência.
3. **Revisão humana onde importa**: o sistema extrai e sugere; a equipe confirma
   pesos e prioridades antes de calcular.

## 2. Os atores (quádrupla hélice)

| Tipo | Quem é | No sistema |
|---|---|---|
| **Startup** | Empresa de base tecnológica | `STARTUP` — setor, solução, maturidade (Ideação → Escala) |
| **Solucionador** | Pessoa física: dev, pesquisador, consultor | `SOLVER` — biografia |
| **Organização** | Empresa que tem uma dor ou demanda | `ORGANIZATION` — ramo de atuação |
| **Governo** | Secretaria, agência de fomento | `GOVERNMENT_AGENCY` — tipo de órgão |

Cada ator tem uma lista de competências, cada uma com uma **força de 0 a 1**
(ex.: Python 1,0; PostgreSQL 0,6).

> Não confunda **ator** com **usuário**. Usuário é quem faz login no sistema
> (Administrador, Editor ou Leitor). Ator é quem participa do ecossistema.

## 3. Arquitetura

```text
                       ┌──────────────────────────────┐
  Navegador ──HTTPS──▶ │  API FastAPI (Python)        │
  (interface /app/)    │  login, validação, regras    │
                       └──┬────────────┬───────────┬──┘
                          │            │           │
              subprocesso │     ctypes │       SQL │
                          ▼            ▼           ▼
                ┌──────────────┐ ┌───────────┐ ┌──────────────┐
                │ Scraper      │ │ Motor C17 │ │ PostgreSQL   │
                │ PDF → JSON   │ │ libariano │ │ 14 tabelas   │
                └──────────────┘ └───────────┘ └──────────────┘
```

| Peça | Tecnologia | Papel |
|---|---|---|
| Interface web | HTML + JS puro, servida pela API em `/app/` | Painel, oportunidades, atores, usuários |
| API | Python, FastAPI, Pydantic | Autenticação, validação, orquestração |
| Scraper | Python, pdfplumber | Lê o edital em PDF e extrai título, prazo, orçamento, competências |
| Motor de matching | C17 puro (sem dependências) | Calcula score, classe e ranking em lote |
| Banco | PostgreSQL 16 | Atores, competências, documentos, demandas, rankings, contas |

**Por que o motor é em C?** É a parte mais crítica e mais testada (57 casos,
~4.800 verificações sob AddressSanitizer). Ele não acessa banco, rede ou arquivo:
recebe dados em memória e devolve resultados. A API o carrega como biblioteca
(`libariano.so`) via `ctypes`.

**Por que o scraper roda em outro processo?** PDF malformado é a maior fonte de
travamento. Em processo separado, o pior caso é um timeout, não a API inteira cair.

## 4. O fluxo, passo a passo

### Passo 1 — Login
O usuário entra com e-mail e senha (guardada com hash scrypt). A sessão vale 12
horas. Perfis:

| Ação | Leitor | Editor | Administrador |
|---|:-:|:-:|:-:|
| Ver painel, demandas, rankings, atores | ✅ | ✅ | ✅ |
| Criar/editar atores e demandas, calcular ranking, enviar PDF | — | ✅ | ✅ |
| Gerenciar perfis de usuários | — | — | ✅ |

Quem se cadastra pela tela entra como **Leitor**; um administrador promove.

### Passo 2 — Visão geral
Painel com documentos processados, demandas abertas, atores ativos, matches
gerados, demandas recentes (com o melhor score) e a distribuição do ecossistema.

### Passo 3 — Nova demanda (com PDF opcional)
1. Em **Oportunidades → Nova demanda**, escolha o PDF do edital e clique em **Ler PDF**.
2. O scraper valida o arquivo (até 10 MB, precisa ser PDF com texto), extrai o
   texto e procura título, prazos, orçamento e competências conhecidas.
3. O JSON completo é salvo em `tb_documents`. Um hash SHA-256 impede processar o
   mesmo PDF duas vezes.
4. O formulário é preenchido com o que foi encontrado, e as competências
   reconhecidas já vêm marcadas.

### Passo 4 — Revisão humana
A equipe confere os campos e, para cada competência, define:
- **Obrigatória** ou **Desejável**;
- **Peso** (importância relativa dentro da demanda).

Escolher peso e prioridade é decisão humana: o sistema só sugere.

### Passo 5 — Calcular ranking
A API busca os atores candidatos (os que têm alguma competência capaz de pontuar),
monta as estruturas e chama `batch_match` no motor em C. O resultado é gravado em
`tb_matches` com a explicação completa em JSON.

### Passo 6 — Ler o resultado
Cada ator no ranking mostra score, classe (**Exata**, **Relacionada**, **Parcial**)
e, ao clicar, o quadro **"Por que este score?"** com a cobertura de cada
competência e de onde veio a evidência.

### Extra — Desempenho (paralelismo)
A página **Desempenho** compara, ao vivo, o motor com 1 thread e com várias
threads (uma barra por thread) e a leitura de editais um de cada vez e vários
ao mesmo tempo (linha do tempo). Detalhes em [docs/PARALELISMO.md](docs/PARALELISMO.md).

## 5. Como o score é calculado

Para cada competência pedida pela demanda, o motor procura evidência no ator:

- **Exata**: o ator tem a própria competência → cobertura = força do ator.
- **Relacionada**: o ator tem uma competência ligada a ela por uma relação
  `origem → alvo` → cobertura = força do ator × peso da relação. Vale a melhor
  relação; nunca soma.
- **Ausente**: nenhuma evidência → cobertura 0.

Depois:

```text
R = média ponderada das coberturas das OBRIGATÓRIAS
D = média ponderada das coberturas das DESEJÁVEIS
score = R × (0,8 + 0,2 × D)      (as desejáveis ajustam até 20% do score)
```

**Exemplo real (demanda de demonstração "Edital de Fomento à Inovação 2026"):**
exige Machine Learning e NLP (obrigatórias) e deseja Computação em Nuvem.

| Ator | Machine Learning | NLP | Nuvem (desejável) | Score |
|---|---|---|---|---|
| Laboratório Alpha | tem, força 1,0 | tem, força 0,9 | tem, força 0,8 | R = 0,95; D = 0,8 → **0,912** (Exata) |
| Startup Beta | tem, força 0,7 | não tem, mas tem LLM (1,0) e LLM → NLP vale 0,9 | não tem | R = 0,80; D = 0 → **0,640** (Relacionada) |
| Construtora Gama | — | — | — | não entra no ranking |

Propriedades garantidas por teste: score entre 0 e 1; desejável nunca compensa
obrigatória ausente; competências extras do ator não mudam o score; empates são
desfeitos sempre da mesma forma. **Scores só se comparam dentro da mesma demanda.**

## 6. O banco de dados

| Tabela | Guarda |
|---|---|
| `tb_actors` + `tb_solvers` / `tb_startups` / `tb_organizations` / `tb_government_agencies` | Atores e os campos de cada tipo |
| `tb_tags`, `tb_tag_relationships` | Competências e relações dirigidas entre elas |
| `tb_actor_tags` | Competências de cada ator, com força |
| `tb_documents` | PDFs processados (JSON completo + hash) |
| `tb_demands`, `tb_demand_tags` | Demandas e competências pedidas, com tipo e peso |
| `tb_matches` | Rankings: score, classe, explicação (JSONB) e versão do algoritmo |
| `tb_users`, `tb_sessions` | Contas e sessões de login |

Quando a API sobe, ela mesma aplica o schema e as migrações (tudo idempotente).
Se o banco estiver vazio, carrega a **demonstração**: atores e demandas fictícios
de Pernambuco, com ranking já calculado. É o que acontece na versão online.

> No Docker Compose local, o próprio Postgres já roda `seed.sql` ao criar o volume,
> então a API encontra o banco preenchido e não carrega a demonstração completa —
> de propósito, para nunca misturar dados fictícios com um banco que já tem dados.

## 7. Rodando no seu computador

Pré-requisito: Docker Desktop aberto. Na pasta `api`:

```bash
docker compose --profile full up -d --build --wait
docker compose --profile full exec api python -m scripts.bootstrap_admin --email voce@exemplo.com
```

O segundo comando pede uma senha (mínimo 12 caracteres). Depois abra
<http://localhost:8000/app/>. A documentação interativa da API fica em
<http://localhost:8000/docs>.

> Não use `docker compose down -v`: o `-v` apaga o volume com os dados.

## 8. Publicação

A versão online roda no **Render** (container com API, scraper e motor) com o
banco no **Neon** (PostgreSQL gerenciado). Passo a passo em
[docs/DEPLOY.md](docs/DEPLOY.md).

## 9. O que existe e o que é visão de futuro

| Implementado | Visão de futuro (ainda não existe no código) |
|---|---|
| Scraper de PDF com regex e seções | OCR para editais escaneados |
| Motor determinístico em C com relações entre tags | Banco de grafos (Neo4j) para relações indiretas |
| API, login, perfis, CRUD de atores, demandas, ranking explicado | Agentes de IA (CrewAI/LangChain) para ler textos livres e gerar o "pitch" do match |
| Interface web e painel | Automações com n8n e notificações |

O ARIANO **não usa nenhum modelo de IA nem serviço pago** no ranking atual: toda a
extração é por regras e todo o matching é aritmética local, por isso é
reprodutível e explicável.

## 10. Para ir mais fundo

- [README da API](api/README.md) — endpoints, decisões e modelo de dados
- [README do motor em C](Matching-ariano-c/matching_engine/README.md) — fórmula completa e semântica das relações
- [README do scraper](scrapper-py/ariano_scraper/README.md) — formato do JSON e limitações
- Documentação das sprints: [02](docs/sprint02/README.md), [03](docs/sprint03/README.md), [04](docs/sprint04/README.md)
