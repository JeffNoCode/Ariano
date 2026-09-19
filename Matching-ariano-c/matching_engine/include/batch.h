/*
 * batch.h - "Encontrar os atores mais compativeis com uma demanda."
 *
 * 1 Demand + N Actors -> N MatchResult -> threshold -> ordenacao -> top_k.
 *
 * OWNERSHIP
 *  - Entradas (actors, demand, relations, config, options): somente leitura;
 *    o batch nunca as altera nem guarda ponteiros para elas.
 *  - BatchResult e dono de `results` E de cada `results[i].details`.
 *    Libere tudo com batch_result_free() (idempotente; aceita NULL).
 *    Nao chame match_result_free() nos itens individuais.
 *  - Em qualquer retorno != MATCHER_OK nada precisa ser liberado.
 *
 * ORDEM (total e deterministica; independe da ordem de entrada dos atores):
 *   1. maior score primeiro (comparado com resolucao de 1e-9);
 *   2. menor required_missing_count;
 *   3. menor actor_id.
 *
 * THRESHOLD: mantem apenas score >= threshold (mesma resolucao de 1e-9).
 *   E so um filtro: nao altera scores. threshold = 0 mantem todos (inclusive score 0).
 * TOP_K: maximo de resultados devolvidos, aplicado APOS threshold e ordenacao.
 *   top_k = 0 significa SEM LIMITE (BATCH_TOP_K_UNLIMITED).
 *
 * O batch NAO exclui atores por required_missing_count > 0 nem por ActorStatus:
 * isso e regra de negocio do chamador (o campo esta em cada MatchResult).
 */
#ifndef ARIANO_BATCH_H
#define ARIANO_BATCH_H

#include "matcher.h"

#define BATCH_TOP_K_UNLIMITED 0

typedef struct {
    double threshold; /* em [0, 1] */
    size_t top_k;     /* 0 = sem limite */
} BatchOptions;

BatchOptions batch_default_options(void); /* threshold 0.0, top_k ilimitado */

typedef struct {
    MatchStatus status;        /* NOT_EVALUABLE se a demanda nao tem tags (results vazio) */
    size_t      evaluated_count; /* atores avaliados                                       */
    size_t      passed_count;    /* atores com score >= threshold (antes do top_k)         */
    size_t      count;           /* tamanho de `results`                                   */
    MatchResult *results;        /* OWNED. Ordenado. NULL se count == 0.                   */
} BatchResult;

/*
 * `actors` pode ser NULL apenas se actor_count == 0.
 * `relations`, `config` e `options` podem ser NULL (padroes).
 *
 * Falha rapida: se UM ator tiver dado invalido, o lote inteiro falha com o
 * codigo do matcher e, se `failed_actor_id` nao for NULL, recebe o id do ator
 * culpado (INT64_MIN para erros que nao sao de um ator especifico, ex.: memoria).
 * Nada e devolvido parcialmente: nenhum resultado e retornado em caso de erro.
 *
 * Demanda sem tags NAO e erro: retorna OK, status NOT_EVALUABLE, count 0.
 */
MatcherError batch_match(const Actor *actors, size_t actor_count, const Demand *demand,
                         const RelationSet *relations, const MatchConfig *config,
                         const BatchOptions *options, BatchResult *out,
                         int64_t *failed_actor_id);

void batch_result_free(BatchResult *result);

#endif /* ARIANO_BATCH_H */
