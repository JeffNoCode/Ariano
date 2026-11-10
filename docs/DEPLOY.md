# Publicando o ARIANO (Render + Neon)

A aplicação inteira (interface, API, scraper e motor em C) roda num único
container Docker no **Render**. O banco PostgreSQL fica no **Neon**. Os dois têm
plano gratuito.

```text
Navegador ──HTTPS──▶ Render (container: API + /app/ + scraper + libariano.so)
                              │
                              └──SSL──▶ Neon (PostgreSQL 16)
```

> **Por que não Vercel/Netlify?** Eles hospedam sites estáticos e funções
> serverless curtas. O ARIANO precisa carregar uma biblioteca em C, executar o
> scraper como subprocesso e manter conexões com o Postgres — isso exige um
> container sempre disponível.

## Limites do plano gratuito

- **Render:** o serviço "dorme" após 15 min sem acesso; o primeiro acesso depois
  disso leva ~1 minuto. Abra o link alguns minutos antes de apresentar.
- **Neon:** 0,5 GB de armazenamento; o banco suspende sozinho quando ocioso e
  acorda em ~1 s (a API já trata conexões derrubadas).

## Passo 1 — Banco no Neon

1. Crie uma conta em <https://neon.tech> (pode entrar com o GitHub).
2. **Create project**: nome `ariano`, PostgreSQL **16 ou 17**, região
   **AWS US East (N. Virginia)** — a mesma do Render, para menor latência.
3. Em **Connection details**, **desligue "Connection pooling"** e copie a
   connection string. Ela tem o formato:
   `postgresql://USUARIO:SENHA@ep-xxxx.us-east-1.aws.neon.tech/neondb?sslmode=require`
   - Use a conexão **direta** (sem `-pooler` no host): a API usa um *advisory
     lock* de sessão ao aplicar as migrações, que não funciona via pooler.
4. Guarde essa string; ela é um segredo (contém a senha do banco).

Não é preciso criar tabelas: a API faz isso na primeira subida.

## Passo 2 — Aplicação no Render

1. Crie uma conta em <https://render.com> e conecte o GitHub.
2. **New → Blueprint** e escolha o repositório `JeffNoCode/Ariano`, branch `main`.
   O Render lê o [`render.yaml`](../render.yaml) da raiz e propõe o serviço `ariano`.
3. Preencha as variáveis marcadas como secretas:

   | Variável | Valor |
   |---|---|
   | `DATABASE_URL` | a connection string do Neon (passo 1) |
   | `ARIANO_ADMIN_EMAIL` | e-mail do primeiro administrador |
   | `ARIANO_ADMIN_PASSWORD` | senha com **12+ caracteres** |

4. **Apply**. O primeiro build compila o motor em C e instala as dependências
   (5–10 min). Acompanhe em **Logs**; a subida correta mostra:

   ```text
   aplicado: schema.sql
   aplicado: 003_auth.sql
   aplicado: 004_scraper_catalog.sql
   aplicado: seed.sql
   aplicado: demo.sql
   ranking inicial gravado para 6 demanda(s)
   administrador voce@exemplo.com: criado
   ```

5. Abra `https://ariano-XXXX.onrender.com` → redireciona para `/app/`. Entre com
   o administrador.

## Passo 3 — Conferir

| Verificação | Esperado |
|---|---|
| `https://.../health` | `{"status":"ok","database":"ok","engine":"ok"}` |
| Visão geral | 6 demandas, 18 atores, rankings já calculados |
| Demanda "Edital de Fomento à Inovação 2026" | Laboratório Alpha **0,912**, Startup Beta **0,640** |
| Nova demanda com PDF | O scraper lê o arquivo e marca as competências reconhecidas |
| `https://.../docs` | Swagger com todos os endpoints |

## Variáveis de ambiente

| Variável | Padrão | Para quê |
|---|---|---|
| `DATABASE_URL` | — | Conexão com o Postgres (obrigatória) |
| `ARIANO_ADMIN_EMAIL` / `ARIANO_ADMIN_PASSWORD` / `ARIANO_ADMIN_NAME` | — | Cria o administrador se ainda não existir. Nunca altera conta existente. |
| `ARIANO_AUTO_MIGRATE` | `true` | `false` impede a API de alterar o banco na subida |
| `ARIANO_SEED_DEMO` | `true` | `false` sobe com o banco vazio (sem dados fictícios) |
| `ARIANO_POOL_MAX` | `10` (`5` no Render) | Conexões simultâneas ao banco |
| `ARIANO_SCRAPER_TIMEOUT` | `120` | Segundos máximos para ler um PDF |
| `PORT` | `8000` | Porta HTTP (o Render define sozinho) |

## Atualizações

Com `autoDeploy: true`, cada push na `main` gera um novo deploy. Migrações novas
vão em `api/db/migrations/NNN_nome.sql` e precisam ser idempotentes
(`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`): elas rodam a cada subida.

## Cuidados antes de divulgar o link

- **Qualquer pessoa pode criar conta** pela tela de login; ela entra como
  **Leitor** (só consulta). Para uma demo pública isso é aceitável; para uso real,
  restrinja o cadastro.
- Ainda não há limite de tentativas de login nem recuperação de senha por e-mail
  (ver próximos passos da Sprint 04).
- Os dados da demonstração são **fictícios**; os nomes terminados em "(demo)" e as
  startups inventadas não representam entidades reais.
- Para zerar a demonstração: no Neon, **Branches → Reset** (ou apague e recrie o
  banco) e reinicie o serviço no Render.
