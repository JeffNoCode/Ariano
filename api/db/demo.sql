-- ARIANO — carga de demonstração
--
-- Dados FICTÍCIOS para apresentar o sistema: nomes de pessoas, startups,
-- organizações e órgãos foram inventados e não representam entidades reais.
-- Nenhum documento (CPF/CNPJ) é cadastrado.
--
-- Aplicada pela API na subida apenas quando o banco está vazio e
-- ARIANO_SEED_DEMO=true (padrão), logo depois de seed.sql. Depois dela a API
-- calcula e grava o ranking de cada demanda, para o painel já abrir com dados.

BEGIN;

-- ------------------------------------------------------------ competências
INSERT INTO tb_tags (code, name, category) VALUES
    ('DATA_ANALYTICS', 'Análise de Dados',             'Dados'),
    ('GIS',            'Geoprocessamento',             'Cidades Inteligentes'),
    ('MOBILE',         'Aplicativos Móveis',           'Desenvolvimento'),
    ('REACT',          'React',                        'Desenvolvimento'),
    ('NODEJS',         'Node.js',                      'Desenvolvimento'),
    ('UX_DESIGN',      'UX / Design de Serviços',      'Design'),
    ('CYBERSECURITY',  'Segurança da Informação',      'Tecnologia'),
    ('HEALTHTECH',     'Saúde Digital',                'Setorial'),
    ('EDTECH',         'Tecnologia Educacional',       'Setorial'),
    ('ENERGY',         'Energia Renovável',            'Setorial')
ON CONFLICT (code) DO NOTHING;

INSERT INTO tb_tag_relationships (source_tag_id, target_tag_id, relation_type, weight)
SELECT s.id, t.id, v.relation_type, v.weight
  FROM (VALUES
          ('MACHINE_LEARNING', 'DATA_ANALYTICS', 'RELATED', 0.7),
          ('PYTHON',           'DATA_ANALYTICS', 'RELATED', 0.5),
          ('REACT',            'MOBILE',         'RELATED', 0.5),
          ('NODEJS',           'WHATSAPP',       'RELATED', 0.4),
          ('IOT',              'GIS',            'RELATED', 0.4),
          ('IOT',              'ENERGY',         'RELATED', 0.5)
       ) AS v(source_code, target_code, relation_type, weight)
  JOIN tb_tags s ON s.code = v.source_code
  JOIN tb_tags t ON t.code = v.target_code
ON CONFLICT DO NOTHING;

-- ------------------------------------------------------------------ atores
INSERT INTO tb_actors (actor_type, name, description, status, city, state) VALUES
    ('GOVERNMENT_AGENCY', 'Secretaria Municipal de Inovação (demo)',  'Órgão fictício que publica desafios cívicos.',            'ACTIVE', 'Recife',    'PE'),
    ('GOVERNMENT_AGENCY', 'Agência Estadual de Fomento (demo)',       'Agência fictícia de fomento à pesquisa e inovação.',     'ACTIVE', 'Recife',    'PE'),
    ('ORGANIZATION',      'Clínica Vida Plena (demo)',                'Rede fictícia de clínicas com alta demanda de agendamento.', 'ACTIVE', 'Olinda', 'PE'),
    ('ORGANIZATION',      'Cooperativa Agreste Solar (demo)',         'Cooperativa fictícia de energia no interior.',           'ACTIVE', 'Caruaru',   'PE'),
    ('STARTUP',           'Maré Analytics',                           'Startup fictícia de dados urbanos e mobilidade.',        'ACTIVE', 'Recife',    'PE'),
    ('STARTUP',           'ZapAtende',                                'Startup fictícia de atendimento automatizado por WhatsApp.', 'ACTIVE', 'Recife', 'PE'),
    ('STARTUP',           'Sertão IoT',                               'Startup fictícia de sensores e telemetria.',             'ACTIVE', 'Petrolina', 'PE'),
    ('STARTUP',           'Escola+ Digital',                          'Startup fictícia de plataformas educacionais.',          'ACTIVE', 'Jaboatão dos Guararapes', 'PE'),
    ('STARTUP',           'Frevo Labs',                               'Startup fictícia de IA generativa para serviços públicos.', 'ACTIVE', 'Recife', 'PE'),
    ('SOLVER',            'Ana Beatriz Lins (demo)',                  'Cientista de dados fictícia.',                           'ACTIVE', 'Recife',    'PE'),
    ('SOLVER',            'Carlos Eduardo Mota (demo)',               'Desenvolvedor back-end fictício.',                       'ACTIVE', 'Olinda',    'PE'),
    ('SOLVER',            'Juliana Freitas (demo)',                   'Designer de serviços fictícia.',                         'ACTIVE', 'Recife',    'PE'),
    ('SOLVER',            'Rafael Antunes (demo)',                    'Especialista fictício em segurança da informação.',      'INACTIVE', 'Paulista', 'PE'),
    ('ORGANIZATION',      'Instituto Capibaribe de Pesquisa (demo)',  'Instituto fictício de pesquisa aplicada.',               'ACTIVE', 'Recife',    'PE');

INSERT INTO tb_government_agencies (actor_id, agency_type)
SELECT id, v.agency_type FROM tb_actors a
  JOIN (VALUES ('Secretaria Municipal de Inovação (demo)', 'Secretaria Municipal'),
               ('Agência Estadual de Fomento (demo)',      'Agência de Fomento')) AS v(name, agency_type)
    ON v.name = a.name;

INSERT INTO tb_organizations (actor_id, business_sector)
SELECT id, v.sector FROM tb_actors a
  JOIN (VALUES ('Clínica Vida Plena (demo)',               'Saúde'),
               ('Cooperativa Agreste Solar (demo)',        'Energia'),
               ('Instituto Capibaribe de Pesquisa (demo)', 'Pesquisa aplicada')) AS v(name, sector)
    ON v.name = a.name;

INSERT INTO tb_startups (actor_id, sector, solution_description, maturity_level)
SELECT id, v.sector, v.solution, v.maturity FROM tb_actors a
  JOIN (VALUES ('Maré Analytics',  'Cidades Inteligentes', 'Painéis de mobilidade e georreferenciamento.',   'GROWTH'),
               ('ZapAtende',       'Atendimento',          'Chatbot com triagem e agendamento por WhatsApp.', 'SCALE'),
               ('Sertão IoT',      'Energia e Agro',       'Sensores de baixo custo e telemetria.',           'MVP'),
               ('Escola+ Digital', 'Educação',             'Trilhas de aprendizagem adaptativas.',            'GROWTH'),
               ('Frevo Labs',      'GovTech',              'Assistentes com LLM para serviços públicos.',     'MVP')) AS v(name, sector, solution, maturity)
    ON v.name = a.name;

INSERT INTO tb_solvers (actor_id, bio)
SELECT id, v.bio FROM tb_actors a
  JOIN (VALUES ('Ana Beatriz Lins (demo)',    'Machine learning, Python e análise de dados públicos.'),
               ('Carlos Eduardo Mota (demo)', 'APIs em Java/Spring Boot e Node.js, integrações com WhatsApp.'),
               ('Juliana Freitas (demo)',     'Pesquisa com usuários, UX e prototipação de serviços.'),
               ('Rafael Antunes (demo)',      'Segurança da informação e LGPD.')) AS v(name, bio)
    ON v.name = a.name;

INSERT INTO tb_actor_tags (actor_id, tag_id, weight)
SELECT a.id, t.id, v.w
  FROM (VALUES
    ('Maré Analytics', 'DATA_ANALYTICS', 1.0), ('Maré Analytics', 'GIS', 0.9), ('Maré Analytics', 'PYTHON', 0.8), ('Maré Analytics', 'CLOUD', 0.7),
    ('ZapAtende', 'WHATSAPP', 1.0), ('ZapAtende', 'AUTOMATION', 0.9), ('ZapAtende', 'NODEJS', 0.8), ('ZapAtende', 'LLM', 0.6), ('ZapAtende', 'POSTGRESQL', 0.7),
    ('Sertão IoT', 'IOT', 1.0), ('Sertão IoT', 'ENERGY', 0.8), ('Sertão IoT', 'CLOUD', 0.6), ('Sertão IoT', 'PYTHON', 0.5),
    ('Escola+ Digital', 'EDTECH', 1.0), ('Escola+ Digital', 'REACT', 0.8), ('Escola+ Digital', 'MOBILE', 0.7), ('Escola+ Digital', 'UX_DESIGN', 0.6),
    ('Frevo Labs', 'LLM', 1.0), ('Frevo Labs', 'NLP', 0.9), ('Frevo Labs', 'AI', 0.9), ('Frevo Labs', 'PYTHON', 0.8), ('Frevo Labs', 'CLOUD', 0.6),
    ('Ana Beatriz Lins (demo)', 'MACHINE_LEARNING', 0.9), ('Ana Beatriz Lins (demo)', 'PYTHON', 1.0), ('Ana Beatriz Lins (demo)', 'DATA_ANALYTICS', 0.9), ('Ana Beatriz Lins (demo)', 'POSTGRESQL', 0.6),
    ('Carlos Eduardo Mota (demo)', 'JAVA', 0.9), ('Carlos Eduardo Mota (demo)', 'SPRING_BOOT', 0.9), ('Carlos Eduardo Mota (demo)', 'NODEJS', 0.7), ('Carlos Eduardo Mota (demo)', 'WHATSAPP', 0.6), ('Carlos Eduardo Mota (demo)', 'POSTGRESQL', 0.8),
    ('Juliana Freitas (demo)', 'UX_DESIGN', 1.0), ('Juliana Freitas (demo)', 'REACT', 0.5), ('Juliana Freitas (demo)', 'HEALTHTECH', 0.4),
    ('Rafael Antunes (demo)', 'CYBERSECURITY', 1.0), ('Rafael Antunes (demo)', 'CLOUD', 0.7),
    ('Instituto Capibaribe de Pesquisa (demo)', 'MACHINE_LEARNING', 0.8), ('Instituto Capibaribe de Pesquisa (demo)', 'HEALTHTECH', 0.9), ('Instituto Capibaribe de Pesquisa (demo)', 'DATA_ANALYTICS', 0.8), ('Instituto Capibaribe de Pesquisa (demo)', 'AI', 0.7)
  ) AS v(actor_name, tag_code, w)
  JOIN tb_actors a ON a.name = v.actor_name
  JOIN tb_tags   t ON t.code = v.tag_code;

-- ---------------------------------------------------------------- demandas
INSERT INTO tb_demands (requester_id, title, description, status, deadline, budget)
SELECT a.id, v.title, v.description, v.status, v.deadline::date, v.budget
  FROM (VALUES
    ('Secretaria Municipal de Inovação (demo)', 'Desafio Mobilidade Urbana Inteligente',
     'Painel de dados de mobilidade com mapas e indicadores para a gestão municipal.', 'OPEN', '2027-02-28', 250000.00),
    ('Clínica Vida Plena (demo)', 'Triagem e agendamento por WhatsApp',
     'Automatizar o agendamento e a triagem inicial de pacientes por WhatsApp.', 'OPEN', '2027-01-15', 80000.00),
    ('Agência Estadual de Fomento (demo)', 'Chamada IA para Serviços Públicos',
     'Assistentes de IA generativa para atendimento ao cidadão.', 'EVALUATING', '2027-03-31', 600000.00),
    ('Cooperativa Agreste Solar (demo)', 'Monitoramento de usinas solares',
     'Sensores e telemetria para geração distribuída no Agreste.', 'OPEN', '2027-04-30', 150000.00),
    ('Secretaria Municipal de Inovação (demo)', 'Plataforma de reforço escolar',
     'Aplicativo de trilhas de aprendizagem para a rede municipal.', 'CLOSED', '2026-08-31', 120000.00)
  ) AS v(requester, title, description, status, deadline, budget)
  JOIN tb_actors a ON a.name = v.requester;

INSERT INTO tb_demand_tags (demand_id, tag_id, tag_type, weight)
SELECT d.id, t.id, v.tag_type, v.w
  FROM (VALUES
    ('Desafio Mobilidade Urbana Inteligente', 'DATA_ANALYTICS', 'REQUIRED', 1.0),
    ('Desafio Mobilidade Urbana Inteligente', 'GIS',            'REQUIRED', 0.8),
    ('Desafio Mobilidade Urbana Inteligente', 'CLOUD',          'DESIRABLE', 1.0),
    ('Triagem e agendamento por WhatsApp',    'WHATSAPP',       'REQUIRED', 1.0),
    ('Triagem e agendamento por WhatsApp',    'AUTOMATION',     'REQUIRED', 1.0),
    ('Triagem e agendamento por WhatsApp',    'POSTGRESQL',     'DESIRABLE', 0.5),
    ('Triagem e agendamento por WhatsApp',    'HEALTHTECH',     'DESIRABLE', 1.0),
    ('Chamada IA para Serviços Públicos',     'AI',             'REQUIRED', 1.0),
    ('Chamada IA para Serviços Públicos',     'NLP',            'REQUIRED', 1.0),
    ('Chamada IA para Serviços Públicos',     'CYBERSECURITY',  'DESIRABLE', 1.0),
    ('Monitoramento de usinas solares',       'IOT',            'REQUIRED', 1.0),
    ('Monitoramento de usinas solares',       'ENERGY',         'REQUIRED', 1.0),
    ('Monitoramento de usinas solares',       'DATA_ANALYTICS', 'DESIRABLE', 1.0),
    ('Plataforma de reforço escolar',         'EDTECH',         'REQUIRED', 1.0),
    ('Plataforma de reforço escolar',         'MOBILE',         'REQUIRED', 0.7),
    ('Plataforma de reforço escolar',         'UX_DESIGN',      'DESIRABLE', 1.0)
  ) AS v(title, tag_code, tag_type, w)
  JOIN tb_demands d ON d.title = v.title
  JOIN tb_tags    t ON t.code  = v.tag_code;

COMMIT;
