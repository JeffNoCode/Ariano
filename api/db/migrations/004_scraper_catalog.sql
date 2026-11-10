-- ARIANO — 004: catálogo alinhado ao scraper
--
-- O scraper reconhece competências pelos códigos de
-- scrapper-py/ariano_scraper/parser/known_tags.json. Para que o PDF possa
-- pré-selecionar competências na tela de Nova demanda, cada um desses códigos
-- precisa existir em tb_tags. Idempotente: pode rodar a cada subida da API.

BEGIN;

INSERT INTO tb_tags (code, name, category) VALUES
    ('AI',               'Inteligência Artificial',              'Tecnologia'),
    ('MACHINE_LEARNING', 'Machine Learning',                     'Tecnologia'),
    ('LLM',              'Modelos de Linguagem de Grande Porte', 'Tecnologia'),
    ('NLP',              'Processamento de Linguagem Natural',   'Tecnologia'),
    ('CLOUD',            'Computação em Nuvem',                  'Tecnologia'),
    ('PYTHON',           'Python',                               'Desenvolvimento'),
    ('JAVA',             'Java',                                 'Desenvolvimento'),
    ('SPRING',           'Spring',                               'Desenvolvimento'),
    ('SPRING_BOOT',      'Spring Boot',                          'Desenvolvimento'),
    ('POSTGRESQL',       'PostgreSQL',                           'Dados'),
    ('WHATSAPP',         'Integração com WhatsApp',              'Atendimento'),
    ('AUTOMATION',       'Automação de Processos',               'Atendimento'),
    ('IOT',              'Internet das Coisas',                  'Cidades Inteligentes'),
    ('BLOCKCHAIN',       'Blockchain',                           'Tecnologia')
ON CONFLICT (code) DO NOTHING;

-- Relações dirigidas (source -> target: "ter source é evidência de target").
INSERT INTO tb_tag_relationships (source_tag_id, target_tag_id, relation_type, weight)
SELECT s.id, t.id, v.relation_type, v.weight
  FROM (VALUES
          ('MACHINE_LEARNING', 'AI',          'RELATED', 0.8),
          ('LLM',              'AI',          'RELATED', 0.8),
          ('NLP',              'AI',          'RELATED', 0.7),
          ('SPRING_BOOT',      'SPRING',      'RELATED', 0.9),
          ('SPRING',           'JAVA',        'RELATED', 0.7),
          ('SPRING_BOOT',      'JAVA',        'RELATED', 0.7),
          ('WHATSAPP',         'AUTOMATION',  'RELATED', 0.6)
       ) AS v(source_code, target_code, relation_type, weight)
  JOIN tb_tags s ON s.code = v.source_code
  JOIN tb_tags t ON t.code = v.target_code
ON CONFLICT DO NOTHING;

COMMIT;
