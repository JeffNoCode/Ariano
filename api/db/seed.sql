-- Dados mínimos para experimentar a API sem cadastrar nada à mão.
--   psql "$DATABASE_URL" -f db/seed.sql
--
-- Monta o cenário: uma demanda (solicitada por um órgão de governo) que exige
-- ML e NLP (e deseja CLOUD), e três atores em situações diferentes — um com
-- tudo, um que só chega via relação LLM → NLP, e um que não tem nada do que
-- se pede.

BEGIN;

INSERT INTO tb_tags (code, name, category) VALUES
    ('MACHINE_LEARNING', 'Machine Learning',                    'Tecnologia'),
    ('NLP',              'Processamento de Linguagem Natural',  'Tecnologia'),
    ('LLM',              'Modelos de Linguagem de Grande Porte','Tecnologia'),
    ('CLOUD',            'Computação em Nuvem',                 'Tecnologia'),
    ('CIVIL_ENG',        'Engenharia Civil',                    'Engenharia')
ON CONFLICT (code) DO NOTHING;

-- LLM → NLP: quem tem LLM demonstra evidência (forte, 0.9) de NLP.
-- A volta não vale: quem só tem NLP continua MISSING numa demanda de LLM.
INSERT INTO tb_tag_relationships (source_tag_id, target_tag_id, relation_type, weight)
SELECT s.id, t.id, 'RELATED', 0.9
  FROM tb_tags s, tb_tags t
 WHERE s.code = 'LLM' AND t.code = 'NLP'
ON CONFLICT DO NOTHING;

-- Solicitante: um órgão de governo (requester_id da demanda abaixo).
INSERT INTO tb_actors (actor_type, name, status)
VALUES ('GOVERNMENT_AGENCY', 'Secretaria de Inovação', 'ACTIVE');
INSERT INTO tb_government_agencies (actor_id, agency_type)
SELECT id, 'Secretaria Estadual' FROM tb_actors WHERE name = 'Secretaria de Inovação';

-- Alpha (organização): tem exatamente o que a demanda exige, força total.
INSERT INTO tb_actors (actor_type, name, status)
VALUES ('ORGANIZATION', 'Laboratório Alpha', 'ACTIVE');
INSERT INTO tb_organizations (actor_id, business_sector)
SELECT id, 'Pesquisa aplicada' FROM tb_actors WHERE name = 'Laboratório Alpha';

-- Beta (startup): não tem NLP, mas tem LLM — deve ser coberta via relação.
INSERT INTO tb_actors (actor_type, name, status)
VALUES ('STARTUP', 'Startup Beta', 'ACTIVE');
INSERT INTO tb_startups (actor_id, sector, maturity_level)
SELECT id, 'IA aplicada', 'GROWTH' FROM tb_actors WHERE name = 'Startup Beta';

-- Gama (organização): nada a ver com a demanda. Só aparece com evaluate_all_actors=true.
INSERT INTO tb_actors (actor_type, name, status)
VALUES ('ORGANIZATION', 'Construtora Gama', 'ACTIVE');
INSERT INTO tb_organizations (actor_id, business_sector)
SELECT id, 'Construção civil' FROM tb_actors WHERE name = 'Construtora Gama';

INSERT INTO tb_actor_tags (actor_id, tag_id, weight)
SELECT a.id, t.id, v.w
  FROM tb_actors a, tb_tags t,
       (VALUES ('MACHINE_LEARNING', 1.0), ('NLP', 0.9), ('CLOUD', 0.8)) AS v(code, w)
 WHERE a.name = 'Laboratório Alpha' AND t.code = v.code;

INSERT INTO tb_actor_tags (actor_id, tag_id, weight)
SELECT a.id, t.id, v.w
  FROM tb_actors a, tb_tags t,
       (VALUES ('MACHINE_LEARNING', 0.7), ('LLM', 1.0)) AS v(code, w)
 WHERE a.name = 'Startup Beta' AND t.code = v.code;

INSERT INTO tb_actor_tags (actor_id, tag_id, weight)
SELECT a.id, t.id, 1.0
  FROM tb_actors a, tb_tags t
 WHERE a.name = 'Construtora Gama' AND t.code = 'CIVIL_ENG';

INSERT INTO tb_demands (requester_id, title, status, deadline, budget)
SELECT id, 'Edital de Fomento à Inovação 2026', 'OPEN', '2026-10-30', 1500000.00
  FROM tb_actors WHERE name = 'Secretaria de Inovação';

INSERT INTO tb_demand_tags (demand_id, tag_id, tag_type, weight)
SELECT d.id, t.id, v.tag_type, v.w
  FROM tb_demands d, tb_tags t,
       (VALUES ('MACHINE_LEARNING', 'REQUIRED', 1.0),
               ('NLP',              'REQUIRED', 1.0),
               ('CLOUD',            'DESIRABLE', 1.0)) AS v(code, tag_type, w)
 WHERE d.title = 'Edital de Fomento à Inovação 2026' AND t.code = v.code;

COMMIT;
