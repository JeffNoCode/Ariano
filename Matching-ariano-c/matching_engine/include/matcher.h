/*
 * matcher.h - API publica do motor de matching.
 */
#ifndef ARIANO_MATCHER_H
#define ARIANO_MATCHER_H

#include "domain.h"

#define MATCHER_ALGORITHM_VERSION "mvp-1"

typedef enum {
    MATCHER_OK = 0,
    MATCHER_ERR_NULL_ARG,
    MATCHER_ERR_INVALID_CONFIG,
    MATCHER_ERR_INVALID_TAG_ID,
    MATCHER_ERR_INVALID_WEIGHT,
    MATCHER_ERR_INVALID_TAG_TYPE,
    MATCHER_ERR_DUPLICATE_TAG,
    MATCHER_ERR_NO_MEMORY,
    MATCHER_ERR_INVALID_OPTIONS, /* batch: threshold fora de [0,1] */
    MATCHER_ERR_DUPLICATE_ACTOR  /* batch: actor_id repetido      */
} MatcherError;

/* Parametros da formula. Ponto unico de ajuste das decisoes de negocio. */
typedef struct {
    /* Fracao do score que DESIRABLE pode modular, em [0, 1].
     * score = R * ((1 - share) + share * D)   quando ha REQUIRED e DESIRABLE.
     *   share = 0 -> score = R          (DESIRABLE ignorado)
     *   share = 1 -> score = R * D      (DESIRABLE passa a ser multiplicador total)
     * Sem REQUIRED ou sem DESIRABLE, share e irrelevante (ver matcher.c). */
    double desirable_share;
} MatchConfig;

const char *matcher_algorithm_version(void);

MatchConfig matcher_default_config(void); /* desirable_share = 0.20 */

/* Validadores independentes (o batch os usa uma vez, antes de avaliar N atores). */
MatcherError matcher_validate_config(const MatchConfig *config);
MatcherError matcher_validate_demand(const Demand *demand);

/*
 * Calcula o matching de UM ator contra UMA demanda.
 *
 *  - `relations` pode ser NULL (equivale a nenhuma relacao).
 *  - `config` pode ser NULL (usa matcher_default_config()).
 *  - Em qualquer retorno != MATCHER_OK, *out fica zerado e nada precisa ser liberado.
 *  - Em MATCHER_OK, o chamador deve chamar match_result_free(out).
 *  - Demanda sem tags NAO e erro: retorna OK com status NOT_EVALUABLE.
 */
MatcherError matcher_run(const Actor *actor, const Demand *demand,
                         const RelationSet *relations, const MatchConfig *config,
                         MatchResult *out);

/* Idempotente: pode ser chamada duas vezes e com NULL sem risco (sem double free). */
void match_result_free(MatchResult *result);

/* Acessores para os dois grupos dentro de `details` (NULL se o grupo e vazio). */
const MatchDetail *match_result_required(const MatchResult *r);
const MatchDetail *match_result_desirable(const MatchResult *r);

const char *matcher_strerror(MatcherError err);

#endif /* ARIANO_MATCHER_H */
