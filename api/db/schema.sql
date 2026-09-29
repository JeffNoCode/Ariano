-- ARIANO — schema PostgreSQL (v2, alinhado ao ERD de atores por subtipo)
--
-- Convenções:
--   * enums como TEXT + CHECK: mais barato adicionar um valor depois do que
--     mexer num tipo ENUM nativo dentro de transação. O mapeamento para os
--     ints do C fica explícito em engine/bindings.py, num lugar só.
--   * tag.code limitado a 63 caracteres: TAG_CODE_MAX no C é 64 com o '\0'.
--
-- Extensões em relação ao ERD (documentadas onde aparecem):
--   * tb_documents: não está no ERD, mas o upload de PDF (POST /documents)
--     depende de guardar o JSON do scraper em algum lugar. Linkada em
--     tb_demands.document_id, nullable.
--   * tb_demands.budget/deadline/currency: não estão no ERD; mantidas porque
--     são dados reais de edital que a API já expunha.
--   * tb_matches.algorithm_version: não está no ERD; necessária para o
--     motor poder evoluir (mvp-1, mvp-2...) sem apagar histórico — ver
--     comentário na tabela.
--
-- Aplicar:  psql "$DATABASE_URL" -f db/schema.sql

BEGIN;

-- ------------------------------------------------------------------ atores

CREATE TABLE IF NOT EXISTS tb_actors (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_type   TEXT NOT NULL
                 CHECK (actor_type IN ('SOLVER','STARTUP','ORGANIZATION','GOVERNMENT_AGENCY')),
    name         TEXT NOT NULL,
    description  TEXT,
    document     TEXT,                      -- CPF ou CNPJ, conforme document_type
    document_type TEXT CHECK (document_type IN ('CPF','CNPJ')),
    status       TEXT NOT NULL DEFAULT 'ACTIVE'
                 CHECK (status IN ('ACTIVE','INACTIVE','SUSPENDED')),
    city         TEXT,
    state        CHAR(2),                   -- UF
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT document_matches_type
        CHECK (document IS NULL OR document_type IS NOT NULL)
);

-- Uma tabela de subtipo por actor_type, 1:1 com tb_actors (mesma PK, que
-- também é FK). Cada ator tem exatamente UMA linha na tabela de subtipo
-- correspondente ao seu actor_type — garantido pelos triggers abaixo, porque
-- o Postgres não tem CHECK que enxergue outra tabela.

CREATE TABLE IF NOT EXISTS tb_solvers (
    actor_id BIGINT PRIMARY KEY REFERENCES tb_actors(id) ON DELETE CASCADE,
    bio      TEXT
);

CREATE TABLE IF NOT EXISTS tb_startups (
    actor_id              BIGINT PRIMARY KEY REFERENCES tb_actors(id) ON DELETE CASCADE,
    sector                TEXT,
    solution_description  TEXT,
    -- valores provisórios: ajuste conforme a régua de maturidade que vocês adotarem
    maturity_level        TEXT CHECK (maturity_level IN ('IDEATION','MVP','GROWTH','SCALE'))
);

CREATE TABLE IF NOT EXISTS tb_organizations (
    actor_id        BIGINT PRIMARY KEY REFERENCES tb_actors(id) ON DELETE CASCADE,
    business_sector TEXT
);

CREATE TABLE IF NOT EXISTS tb_government_agencies (
    actor_id    BIGINT PRIMARY KEY REFERENCES tb_actors(id) ON DELETE CASCADE,
    agency_type TEXT
);

-- Impede órfãos e tipos trocados: um INSERT em tb_startups para um ator cujo
-- actor_type não é 'STARTUP' falha; e trocar tb_actors.actor_type depois de
-- criado falha também (para trocar, apague a linha de subtipo antiga e crie
-- a nova — é uma mudança de identidade do ator, não um update trivial).
CREATE OR REPLACE FUNCTION ariano_check_actor_subtype()
RETURNS TRIGGER AS $$
DECLARE
    expected TEXT;
    actual   TEXT;
BEGIN
    expected := TG_ARGV[0];
    SELECT actor_type INTO actual FROM tb_actors WHERE id = NEW.actor_id;
    IF actual IS NULL THEN
        RAISE EXCEPTION 'actor_id % não existe em tb_actors', NEW.actor_id;
    END IF;
    IF actual <> expected THEN
        RAISE EXCEPTION 'actor_id % tem actor_type % mas foi inserido em %  (esperado %)',
            NEW.actor_id, actual, TG_TABLE_NAME, expected;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_check_solver_type ON tb_solvers;
CREATE TRIGGER trg_check_solver_type
    BEFORE INSERT OR UPDATE ON tb_solvers
    FOR EACH ROW EXECUTE FUNCTION ariano_check_actor_subtype('SOLVER');

DROP TRIGGER IF EXISTS trg_check_startup_type ON tb_startups;
CREATE TRIGGER trg_check_startup_type
    BEFORE INSERT OR UPDATE ON tb_startups
    FOR EACH ROW EXECUTE FUNCTION ariano_check_actor_subtype('STARTUP');

DROP TRIGGER IF EXISTS trg_check_organization_type ON tb_organizations;
CREATE TRIGGER trg_check_organization_type
    BEFORE INSERT OR UPDATE ON tb_organizations
    FOR EACH ROW EXECUTE FUNCTION ariano_check_actor_subtype('ORGANIZATION');

DROP TRIGGER IF EXISTS trg_check_government_agency_type ON tb_government_agencies;
CREATE TRIGGER trg_check_government_agency_type
    BEFORE INSERT OR UPDATE ON tb_government_agencies
    FOR EACH ROW EXECUTE FUNCTION ariano_check_actor_subtype('GOVERNMENT_AGENCY');

-- ------------------------------------------------------------ competências

CREATE TABLE IF NOT EXISTS tb_tags (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        VARCHAR(63) NOT NULL UNIQUE,
    name        TEXT        NOT NULL,
    category    TEXT,
    subcategory TEXT,
    is_active   BOOLEAN     NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Relação DIRECIONADA source -> target: "possuir source é evidência de target".
-- A inversa não é implícita, nem para SYNONYM (o motor não cria relação reversa).
--
-- relation_type faz parte da chave: diferente da v1 deste schema, agora é
-- possível ter, por exemplo, RELATED *e* SYNONYM entre o mesmo par de tags
-- ao mesmo tempo (o motor, ao escolher a melhor cobertura por tag, já lida
-- com isso — SYNONYM desempata na frente de RELATED). Isso é o que o ERD
-- pede ao colocar relation_type na chave primária.
CREATE TABLE IF NOT EXISTS tb_tag_relationships (
    source_tag_id  BIGINT      NOT NULL REFERENCES tb_tags(id) ON DELETE CASCADE,
    target_tag_id  BIGINT      NOT NULL REFERENCES tb_tags(id) ON DELETE CASCADE,
    relation_type  TEXT        NOT NULL CHECK (relation_type IN ('RELATED','SYNONYM','PART_OF')),
    weight         DOUBLE PRECISION NOT NULL CHECK (weight >= 0 AND weight <= 1),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_tag_id, target_tag_id, relation_type),
    CONSTRAINT no_self_relation CHECK (source_tag_id <> target_tag_id)
);

-- O motor busca relações POR TARGET (as tags que a demanda exige).
CREATE INDEX IF NOT EXISTS ix_tag_relationships_target
    ON tb_tag_relationships (target_tag_id);

CREATE TABLE IF NOT EXISTS tb_actor_tags (
    actor_id   BIGINT NOT NULL REFERENCES tb_actors(id) ON DELETE CASCADE,
    tag_id     BIGINT NOT NULL REFERENCES tb_tags(id)   ON DELETE CASCADE,
    -- força da competência; 0 = "declarada, sem evidência" (não cobre nada)
    weight     DOUBLE PRECISION NOT NULL CHECK (weight >= 0 AND weight <= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (actor_id, tag_id)
);

CREATE INDEX IF NOT EXISTS ix_actor_tags_tag ON tb_actor_tags (tag_id);

-- --------------------------------------------------------------- documentos
--
-- Não está no ERD enviado. Mantida porque POST /documents precisa gravar o
-- JSON do scraper em algum lugar rastreável; se vocês decidirem que documento
-- é só um anexo solto, esta tabela pode ser removida e tb_demands.document_id
-- apagado sem afetar o resto do schema.

CREATE TABLE IF NOT EXISTS tb_documents (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_file        TEXT,
    source_url         TEXT,
    document_hash      TEXT        NOT NULL UNIQUE,  -- 'sha256:...' — evita reprocessar
    title              TEXT,
    organization       TEXT,
    parser_version     TEXT        NOT NULL,
    extraction_method  TEXT        NOT NULL,
    ocr_used           BOOLEAN     NOT NULL DEFAULT false,
    page_count         INTEGER,
    payload            JSONB       NOT NULL,
    processed_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------- demandas

CREATE TABLE IF NOT EXISTS tb_demands (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    requester_id   BIGINT REFERENCES tb_actors(id) ON DELETE SET NULL,
    title          TEXT   NOT NULL,
    description    TEXT,
    status         TEXT   NOT NULL DEFAULT 'OPEN'
                   CHECK (status IN ('OPEN','EVALUATING','CLOSED','CANCELLED')),
    -- extensões fora do ERD, ver comentário no topo do arquivo:
    deadline       DATE,
    budget         NUMERIC(18,2),
    currency       CHAR(3) NOT NULL DEFAULT 'BRL',
    document_id    BIGINT REFERENCES tb_documents(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_demands_requester ON tb_demands (requester_id);

CREATE TABLE IF NOT EXISTS tb_demand_tags (
    demand_id  BIGINT NOT NULL REFERENCES tb_demands(id) ON DELETE CASCADE,
    tag_id     BIGINT NOT NULL REFERENCES tb_tags(id)    ON DELETE CASCADE,
    tag_type   TEXT   NOT NULL CHECK (tag_type IN ('REQUIRED','DESIRABLE')),
    -- importância relativa; o motor REJEITA peso 0 (tag sem efeito deve sair da demanda)
    weight     DOUBLE PRECISION NOT NULL CHECK (weight > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (demand_id, tag_id)
);

CREATE INDEX IF NOT EXISTS ix_demand_tags_tag ON tb_demand_tags (tag_id);

-- ------------------------------------------------------------------ matches
--
-- Uma linha por (demanda, ator, versão do algoritmo). `score_details` guarda
-- em jsonb tudo que MatchResult carrega além do score — inclusive o array de
-- MatchDetail por tag, um por item avaliado. Formato:
--
-- {
--   "status": "EVALUATED",
--   "required_score": 0.9, "desirable_score": 0.8,
--   "required_count": 2, "desirable_count": 1, "required_missing_count": 0,
--   "details": [
--     {"demand_tag_id": 1, "tag_type": "REQUIRED", "match": "EXACT",
--      "actor_tag_id": 1, "relation_type": null,
--      "demand_weight": 1.0, "actor_weight": 1.0, "relation_weight": 1.0,
--      "coverage": 1.0}
--   ]
-- }
--
-- Trade-off assumido: dá pra consultar com operadores jsonb do Postgres
-- (`score_details @> '{"status":"EVALUATED"}'`, `jsonb_array_elements`), mas
-- não com índices de coluna comuns. Se "quais matches cobriram a tag X via
-- RELATED" virar uma consulta frequente, um índice GIN em score_details
-- resolve sem precisar voltar para tabela separada.
CREATE TABLE IF NOT EXISTS tb_matches (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    demand_id         BIGINT NOT NULL REFERENCES tb_demands(id) ON DELETE CASCADE,
    actor_id          BIGINT NOT NULL REFERENCES tb_actors(id)  ON DELETE CASCADE,
    score             DOUBLE PRECISION NOT NULL CHECK (score >= 0 AND score <= 1),
    match_type        TEXT   NOT NULL CHECK (match_type IN ('NONE','PARTIAL','RELATED','EXACT')),
    score_details     JSONB  NOT NULL,
    -- não está no ERD; necessária para reprocessar com uma versão nova do
    -- motor (mvp-2...) sem apagar o histórico da anterior — ver README.
    algorithm_version TEXT   NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (demand_id, actor_id, algorithm_version)
);

CREATE INDEX IF NOT EXISTS ix_matches_ranking
    ON tb_matches (demand_id, score DESC, actor_id);
CREATE INDEX IF NOT EXISTS ix_matches_details_gin
    ON tb_matches USING GIN (score_details);

COMMIT;
