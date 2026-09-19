/*
 * domain.h - Tipos de dominio do ARIANO Matching Engine.
 *
 * Regras de ownership (leia antes de usar):
 *  - Actor, Demand, TagCatalog e RelationSet sao VISOES (views) somente-leitura:
 *    guardam ponteiros para arrays que pertencem ao CHAMADOR. O motor nunca
 *    libera nem altera esses arrays, e nunca guarda esses ponteiros depois que
 *    matcher_run() retorna.
 *  - MatchResult e o UNICO tipo que possui memoria alocada (o array `details`).
 *    Deve ser liberado com match_result_free().
 */
#ifndef ARIANO_DOMAIN_H
#define ARIANO_DOMAIN_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define TAG_ID_NONE   ((int64_t)-1) /* "nenhuma tag" (ex.: item MISSING)      */
#define TAG_CODE_MAX  64            /* tamanho maximo do codigo, com o '\0'   */

/* ------------------------------------------------------------------ enums */

typedef enum {
    ACTOR_TYPE_SOLVER = 0,
    ACTOR_TYPE_STARTUP,
    ACTOR_TYPE_ORGANIZATION,
    ACTOR_TYPE_GOVERNMENT_AGENCY
} ActorType;

/* PROVISORIO: os valores reais de tb_actors.status ainda nao foram definidos. */
typedef enum {
    ACTOR_STATUS_ACTIVE = 0,
    ACTOR_STATUS_INACTIVE,
    ACTOR_STATUS_SUSPENDED
} ActorStatus;

typedef enum {
    TAG_TYPE_REQUIRED = 0,
    TAG_TYPE_DESIRABLE
} TagType;

/* Resultado por ITEM (uma tag da demanda). Nao ha PARTIAL neste nivel.
 * Invariante: MISSING <=> coverage == 0 (nao ha evidencia com cobertura > 0). */
typedef enum {
    MATCH_MISSING = 0, /* avaliada; nenhuma correspondencia encontrada */
    MATCH_RELATED,     /* coberta por uma tag relacionada do ator      */
    MATCH_EXACT        /* o ator possui a propria tag                  */
} MatchType;

/* Classificacao do RESULTADO GLOBAL (vai para tb_matches.match_type).
 * Calculada sobre o grupo principal (REQUIRED; DESIRABLE se nao ha REQUIRED).
 * Precedencia: completude primeiro, exatidao depois:
 *   algum MISSING + algum coberto -> PARTIAL;  tudo MISSING -> NONE;
 *   tudo coberto: todos EXACT -> EXACT, senao RELATED.
 * Descreve o TIPO da cobertura, nao sua FORCA (a forca esta no score). */
typedef enum {
    MATCH_CLASS_NONE = 0, /* nenhum item do grupo principal coberto          */
    MATCH_CLASS_PARTIAL,  /* alguns cobertos, outros MISSING                 */
    MATCH_CLASS_RELATED,  /* todos cobertos, ao menos um via RELATED         */
    MATCH_CLASS_EXACT     /* todos cobertos por EXACT                        */
} MatchClass;

/* O resultado foi de fato calculado? (distingue "nao achou" de "nao ha o que achar") */
typedef enum {
    MATCH_STATUS_EVALUATED = 0,
    MATCH_STATUS_NOT_EVALUABLE /* demanda sem nenhuma tag */
} MatchStatus;

typedef enum {
    RELATION_NONE = 0, /* sentinela: "sem relacao"; nunca vem do banco */
    RELATION_RELATED,
    RELATION_SYNONYM,
    RELATION_PART_OF   /* reservado; ignorado pelo motor no MVP */
} RelationType;

/* ----------------------------------------------------------------- structs */

typedef struct {
    int64_t id;
    char    code[TAG_CODE_MAX];
} Tag;

/* Catalogo id->codigo. Usado apenas para exibir/serializar resultados. */
typedef struct {
    const Tag *items;
    size_t     count;
} TagCatalog;

typedef struct {
    int64_t tag_id;
    double  weight; /* forca da competencia do ator, em [0, 1]; 0 = declarada sem evidencia */
} ActorTag;

typedef struct {
    int64_t         id;
    ActorType       type;   /* nao usado no score; mantido p/ o chamador filtrar */
    ActorStatus     status; /* idem: elegibilidade e decisao do chamador         */
    const ActorTag *tags;
    size_t          tag_count;
} Actor;

typedef struct {
    int64_t tag_id;
    TagType type;
    double  weight; /* importancia relativa dentro da demanda, > 0 */
} DemandTag;

typedef struct {
    int64_t          id;
    const DemandTag *tags;
    size_t           tag_count;
} Demand;

/*
 * Relacao DIRECIONADA  source_tag -> target_tag:
 *   "possuir source_tag fornece evidencia de compatibilidade com target_tag".
 * Um ator que possui `source` pode atender uma demanda que exige `target`
 * (ex.: MACHINE_LEARNING -> LLM). A direcao inversa NAO e implicita, nem para
 * SYNONYM: equivalencia nos dois sentidos exige as duas linhas (A->B e B->A).
 */
typedef struct {
    int64_t      source_tag_id;
    int64_t      target_tag_id;
    RelationType type;
    double       weight; /* quanto `source` transfere de evidencia para `target`, em [0, 1] */
} TagRelationship;

typedef struct {
    const TagRelationship *items;
    size_t                 count;
} RelationSet;

/* Uma linha de score_details. Guarda IDs; os codigos vem do TagCatalog. */
typedef struct {
    int64_t      demand_tag_id;
    TagType      tag_type;
    MatchType    match;
    int64_t      actor_tag_id;    /* TAG_ID_NONE se MISSING                     */
    RelationType relation_type;   /* RELATION_NONE se EXACT ou MISSING          */
    double       demand_weight;   /* peso da tag na demanda                     */
    double       actor_weight;    /* 0 se MISSING                               */
    double       relation_weight; /* 1.0 se EXACT, 0 se MISSING                 */
    double       coverage;        /* actor_weight * relation_weight, em [0, 1]  */
} MatchDetail;

typedef struct {
    int64_t     actor_id;
    int64_t     demand_id;
    MatchStatus status;
    double      score;            /* [0, 1] */
    double      required_score;   /* [0, 1]; 0 se nao ha REQUIRED */
    double      desirable_score;  /* [0, 1]; 0 se nao ha DESIRABLE */
    MatchClass  match_class;
    size_t      required_count;
    size_t      desirable_count;
    size_t      required_missing_count;
    /* Possuido pelo resultado. Primeiro os `required_count` itens REQUIRED,
     * depois os `desirable_count` itens DESIRABLE. NULL se nao ha itens. */
    MatchDetail *details;
    const char  *algorithm_version; /* string estatica; nao liberar */
} MatchResult;

/* ---------------------------------------------------------------- helpers */

const char *actor_type_name(ActorType t);
const char *tag_type_name(TagType t);
const char *match_type_name(MatchType t);
const char *match_class_name(MatchClass c);
const char *match_status_name(MatchStatus s);
const char *relation_type_name(RelationType t);

/* Retorna o codigo da tag ou NULL se nao existir. Ponteiro pertence ao catalogo. */
const char *tag_catalog_code(const TagCatalog *catalog, int64_t tag_id);

#endif /* ARIANO_DOMAIN_H */
