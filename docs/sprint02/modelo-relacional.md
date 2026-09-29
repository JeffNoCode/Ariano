# ARIANO - Modelo Relacional da Sprint 02

Fonte: `api/db/schema.sql` (PostgreSQL 16). PK = chave primária; FK = chave estrangeira.
Os campos adicionais ao MER inicial (`tb_documents`, prazo, orçamento, moeda e versão do algoritmo) estão descritos no documento técnico da Sprint 02.

## tb_actors

| Coluna | Tipo SQL | Restrições |
|---|---|---|
| `id` | `BIGINT` | PK, IDENTITY |
| `actor_type` | `TEXT` | NOT NULL |
| `name` | `TEXT` | NOT NULL |
| `description` | `TEXT` | opcional |
| `document` | `TEXT` | opcional |
| `document_type` | `TEXT` | opcional |
| `status` | `TEXT` | NOT NULL, DEFAULT 'ACTIVE' |
| `city` | `TEXT` | opcional |
| `state` | `CHAR(2)` | opcional |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() |

## tb_solvers

| Coluna | Tipo SQL | Restrições |
|---|---|---|
| `actor_id` | `BIGINT` | PK, FK -> tb_actors.id |
| `bio` | `TEXT` | opcional |

## tb_startups

| Coluna | Tipo SQL | Restrições |
|---|---|---|
| `actor_id` | `BIGINT` | PK, FK -> tb_actors.id |
| `sector` | `TEXT` | opcional |
| `solution_description` | `TEXT` | opcional |
| `maturity_level` | `TEXT` | opcional |

## tb_organizations

| Coluna | Tipo SQL | Restrições |
|---|---|---|
| `actor_id` | `BIGINT` | PK, FK -> tb_actors.id |
| `business_sector` | `TEXT` | opcional |

## tb_government_agencies

| Coluna | Tipo SQL | Restrições |
|---|---|---|
| `actor_id` | `BIGINT` | PK, FK -> tb_actors.id |
| `agency_type` | `TEXT` | opcional |

## tb_tags

| Coluna | Tipo SQL | Restrições |
|---|---|---|
| `id` | `BIGINT` | PK, IDENTITY |
| `code` | `VARCHAR(63)` | NOT NULL, UNIQUE |
| `name` | `TEXT` | NOT NULL |
| `category` | `TEXT` | opcional |
| `subcategory` | `TEXT` | opcional |
| `is_active` | `BOOLEAN` | NOT NULL, DEFAULT true |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() |

## tb_tag_relationships

| Coluna | Tipo SQL | Restrições |
|---|---|---|
| `source_tag_id` | `BIGINT` | PK, FK -> tb_tags.id |
| `target_tag_id` | `BIGINT` | PK, FK -> tb_tags.id |
| `relation_type` | `TEXT` | PK |
| `weight` | `DOUBLE PRECISION` | NOT NULL |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() |

## tb_actor_tags

| Coluna | Tipo SQL | Restrições |
|---|---|---|
| `actor_id` | `BIGINT` | PK, FK -> tb_actors.id |
| `tag_id` | `BIGINT` | PK, FK -> tb_tags.id |
| `weight` | `DOUBLE PRECISION` | NOT NULL |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() |

## tb_documents

| Coluna | Tipo SQL | Restrições |
|---|---|---|
| `id` | `BIGINT` | PK, IDENTITY |
| `source_file` | `TEXT` | opcional |
| `source_url` | `TEXT` | opcional |
| `document_hash` | `TEXT` | NOT NULL, UNIQUE |
| `title` | `TEXT` | opcional |
| `organization` | `TEXT` | opcional |
| `parser_version` | `TEXT` | NOT NULL |
| `extraction_method` | `TEXT` | NOT NULL |
| `ocr_used` | `BOOLEAN` | NOT NULL, DEFAULT false |
| `page_count` | `INTEGER` | opcional |
| `payload` | `JSONB` | NOT NULL |
| `processed_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() |

## tb_demands

| Coluna | Tipo SQL | Restrições |
|---|---|---|
| `id` | `BIGINT` | PK, IDENTITY |
| `requester_id` | `BIGINT` | FK -> tb_actors.id |
| `title` | `TEXT` | NOT NULL |
| `description` | `TEXT` | opcional |
| `status` | `TEXT` | NOT NULL, DEFAULT 'OPEN' |
| `deadline` | `DATE` | opcional |
| `budget` | `NUMERIC(18,2)` | opcional |
| `currency` | `CHAR(3)` | NOT NULL, DEFAULT 'BRL' |
| `document_id` | `BIGINT` | FK -> tb_documents.id |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() |

## tb_demand_tags

| Coluna | Tipo SQL | Restrições |
|---|---|---|
| `demand_id` | `BIGINT` | PK, FK -> tb_demands.id |
| `tag_id` | `BIGINT` | PK, FK -> tb_tags.id |
| `tag_type` | `TEXT` | NOT NULL |
| `weight` | `DOUBLE PRECISION` | NOT NULL |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() |

## tb_matches

| Coluna | Tipo SQL | Restrições |
|---|---|---|
| `id` | `BIGINT` | PK, IDENTITY |
| `demand_id` | `BIGINT` | FK -> tb_demands.id, NOT NULL |
| `actor_id` | `BIGINT` | FK -> tb_actors.id, NOT NULL |
| `score` | `DOUBLE PRECISION` | NOT NULL |
| `match_type` | `TEXT` | NOT NULL |
| `score_details` | `JSONB` | NOT NULL |
| `algorithm_version` | `TEXT` | NOT NULL |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT now() |

## Integridade adicional

- `tb_actors`: `actor_type`, `document_type` e `status` possuem CHECK; documento exige `document_type`.
- Os quatro subtipos de ator possuem trigger de validação do `actor_type`.
- `tb_actor_tags.weight`, `tb_tag_relationships.weight` e `tb_matches.score` ficam em [0,1]; `tb_demand_tags.weight` é positivo.
- `tb_tag_relationships` proíbe relação consigo mesma; `relation_type` integra a PK composta.
- `tb_matches` possui UNIQUE (`demand_id`, `actor_id`, `algorithm_version`) e índice GIN em `score_details`.
