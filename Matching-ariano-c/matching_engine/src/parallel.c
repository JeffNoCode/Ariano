#include "parallel.h"

#include <math.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>

#include "alloc.h"

#define ID_UNKNOWN  INT64_MIN
#define SCORE_SCALE 1e9

/* Mesmas regras de ordenacao de batch.c (score com resolucao 1e-9, depois
 * menos obrigatorias faltando, depois menor actor_id): ordem total. */
static int64_t score_key(double score)
{
    return (int64_t)llround(score * SCORE_SCALE);
}

static int result_cmp(const void *x, const void *y)
{
    const MatchResult *a = x, *b = y;
    int64_t ka = score_key(a->score), kb = score_key(b->score);
    if (ka != kb) return (ka > kb) ? -1 : 1;
    if (a->required_missing_count != b->required_missing_count)
        return (a->required_missing_count < b->required_missing_count) ? -1 : 1;
    if (a->actor_id != b->actor_id) return (a->actor_id < b->actor_id) ? -1 : 1;
    return 0;
}

static int cmp_i64(const void *x, const void *y)
{
    int64_t a = *(const int64_t *)x, b = *(const int64_t *)y;
    return (a > b) - (a < b);
}

/* ------------------------------------------------------------- trabalho */

typedef struct {
    const Actor       *actors;
    const Demand      *demand;
    const RelationSet *relations;
    const MatchConfig *cfg;
    MatchResult       *results;  /* compartilhado: cada thread so escreve no seu intervalo */
    unsigned char     *made;     /* 1 = results[i] foi calculado e precisa ser liberado   */
    size_t             lo, hi;
    size_t            *progress; /* &progress[t] ou NULL */
    int64_t            thr_key;  /* threshold em 1e-9                                     */
    size_t             keep;     /* top_k (0 = todos)                                     */
    MatcherError       err;      /* primeiro erro desta thread                            */
    size_t             err_index;
    size_t             passed;   /* quantos passaram do threshold neste trecho            */
    size_t             count;    /* quantos ficaram em results[lo .. lo+count), ordenados  */
} Chunk;

/*
 * Cada thread: avalia seu trecho, descarta quem fica abaixo do threshold,
 * ORDENA o proprio trecho e ja corta no top_k. Assim a parte sequencial do fim
 * (lei de Amdahl) e so juntar T listas ja ordenadas, e nao ordenar tudo.
 */
static void *run_chunk(void *arg)
{
    Chunk *c = arg;
    for (size_t i = c->lo; i < c->hi; i++) {
        MatcherError e = matcher_run(&c->actors[i], c->demand, c->relations, c->cfg, &c->results[i]);
        if (e != MATCHER_OK) {
            c->err = e;
            c->err_index = i;
            break;
        }
        c->made[i] = 1;
        size_t done = i - c->lo + 1;
        if (c->progress != NULL && (done % PARALLEL_PROGRESS_STEP == 0 || i + 1 == c->hi)) {
            __atomic_store_n(c->progress, done, __ATOMIC_RELAXED);
        }
    }
    if (c->err != MATCHER_OK) return NULL; /* limpeza fica com a chamadora */

    MatchResult *seg = &c->results[c->lo];
    size_t n = c->hi - c->lo, kept = 0;
    for (size_t i = 0; i < n; i++) {
        if (score_key(seg[i].score) < c->thr_key) {
            match_result_free(&seg[i]);
        } else {
            seg[kept++] = seg[i];
        }
    }
    c->passed = kept;
    if (kept > 1) qsort(seg, kept, sizeof *seg, result_cmp);
    if (c->keep > 0 && kept > c->keep) {
        for (size_t i = c->keep; i < kept; i++) match_result_free(&seg[i]);
        kept = c->keep;
    }
    c->count = kept;
    return NULL;
}

size_t parallel_effective_threads(size_t n_threads, size_t actor_count)
{
    size_t t = n_threads == 0 ? 1 : n_threads;
    if (t > PARALLEL_MAX_THREADS) t = PARALLEL_MAX_THREADS;
    if (actor_count > 0 && t > actor_count) t = actor_count;
    return t;
}

MatcherError batch_match_parallel(const Actor *actors, size_t actor_count,
                                  const Demand *demand, const RelationSet *relations,
                                  const MatchConfig *config, const BatchOptions *options,
                                  size_t n_threads, size_t *progress,
                                  BatchResult *out, int64_t *failed_actor_id)
{
    /* ---- validacoes identicas as de batch_match ---- */
    if (failed_actor_id != NULL) *failed_actor_id = ID_UNKNOWN;
    if (out == NULL) return MATCHER_ERR_NULL_ARG;
    memset(out, 0, sizeof *out);
    if (demand == NULL || (actor_count > 0 && actors == NULL)) return MATCHER_ERR_NULL_ARG;
    if (relations != NULL && relations->count > 0 && relations->items == NULL) return MATCHER_ERR_NULL_ARG;

    const BatchOptions opt = (options != NULL) ? *options : batch_default_options();
    if (!isfinite(opt.threshold) || opt.threshold < 0.0 || opt.threshold > 1.0)
        return MATCHER_ERR_INVALID_OPTIONS;
    const MatchConfig cfg = (config != NULL) ? *config : matcher_default_config();
    MatcherError err = matcher_validate_config(&cfg);
    if (err != MATCHER_OK) return err;
    err = matcher_validate_demand(demand);
    if (err != MATCHER_OK) return err;

    if (demand->tag_count == 0) {
        out->status = MATCH_STATUS_NOT_EVALUABLE;
        return MATCHER_OK;
    }
    out->status = MATCH_STATUS_EVALUATED;
    if (actor_count == 0) return MATCHER_OK;

    if (actor_count > 1) {
        int64_t *ids = ame_calloc(actor_count, sizeof *ids);
        if (ids == NULL) { memset(out, 0, sizeof *out); return MATCHER_ERR_NO_MEMORY; }
        for (size_t i = 0; i < actor_count; i++) ids[i] = actors[i].id;
        qsort(ids, actor_count, sizeof *ids, cmp_i64);
        for (size_t i = 1; i < actor_count; i++) {
            if (ids[i] == ids[i - 1]) {
                int64_t dup = ids[i];
                free(ids);
                memset(out, 0, sizeof *out);
                if (failed_actor_id != NULL) *failed_actor_id = dup;
                return MATCHER_ERR_DUPLICATE_ACTOR;
            }
        }
        free(ids);
    }

    /* ---- avaliacao em T threads ---- */
    const size_t T = parallel_effective_threads(n_threads, actor_count);
    MatchResult   *results = ame_calloc(actor_count, sizeof *results);
    unsigned char *made    = ame_calloc(actor_count, sizeof *made);
    Chunk         *chunks  = ame_calloc(T, sizeof *chunks);
    pthread_t     *tids    = ame_calloc(T, sizeof *tids);
    unsigned char *started = ame_calloc(T, sizeof *started);
    if (!results || !made || !chunks || !tids || !started) {
        free(results); free(made); free(chunks); free(tids); free(started);
        memset(out, 0, sizeof *out);
        return MATCHER_ERR_NO_MEMORY;
    }

    const int64_t thr_key = score_key(opt.threshold);
    for (size_t t = 0; t < T; t++) {
        chunks[t] = (Chunk){
            .actors = actors, .demand = demand, .relations = relations, .cfg = &cfg,
            .results = results, .made = made,
            .lo = t * actor_count / T, .hi = (t + 1) * actor_count / T,
            .progress = progress ? &progress[t] : NULL,
            .thr_key = thr_key, .keep = opt.top_k,
            .err = MATCHER_OK, .err_index = 0,
        };
        if (progress) __atomic_store_n(&progress[t], (size_t)0, __ATOMIC_RELAXED);
    }
    /* A thread 0 e a propria chamadora; as demais sao criadas. Se a criacao de
     * alguma falhar, o trecho dela roda aqui mesmo, sem alterar o resultado. */
    for (size_t t = 1; t < T; t++) {
        started[t] = pthread_create(&tids[t], NULL, run_chunk, &chunks[t]) == 0;
    }
    run_chunk(&chunks[0]);
    for (size_t t = 1; t < T; t++) {
        if (started[t]) pthread_join(tids[t], NULL);
        else run_chunk(&chunks[t]);
    }

    /* Erro do ator de menor indice = o mesmo erro que o lote sequencial daria. */
    size_t first_bad = actor_count;
    for (size_t t = 0; t < T; t++) {
        if (chunks[t].err != MATCHER_OK && chunks[t].err_index < first_bad) {
            first_bad = chunks[t].err_index;
            err = chunks[t].err;
        }
    }
    free(tids); free(started);

    if (first_bad < actor_count) {
        /* Trechos que terminaram ja liberaram quem nao entrou; os que falharam
         * nao compactaram nada. Libera o que restou de cada um. */
        for (size_t t = 0; t < T; t++) {
            const Chunk *c = &chunks[t];
            if (c->err == MATCHER_OK) {
                for (size_t i = 0; i < c->count; i++) match_result_free(&results[c->lo + i]);
            } else {
                for (size_t i = c->lo; i < c->hi; i++) if (made[i]) match_result_free(&results[i]);
            }
        }
        free(chunks); free(results); free(made);
        memset(out, 0, sizeof *out);
        if (failed_actor_id != NULL)
            *failed_actor_id = (err == MATCHER_ERR_NO_MEMORY) ? ID_UNKNOWN : actors[first_bad].id;
        return err;
    }
    free(made);

    /* ---- junta T listas ordenadas (mesma ordem total do sequencial) ---- */
    size_t passed = 0, available = 0;
    for (size_t t = 0; t < T; t++) { passed += chunks[t].passed; available += chunks[t].count; }
    const size_t cap = (opt.top_k > 0 && opt.top_k < available) ? opt.top_k : available;

    MatchResult *merged = NULL;
    if (cap > 0) {
        merged = ame_calloc(cap, sizeof *merged);
        if (merged == NULL) {
            for (size_t t = 0; t < T; t++)
                for (size_t i = 0; i < chunks[t].count; i++) match_result_free(&results[chunks[t].lo + i]);
            free(chunks); free(results);
            memset(out, 0, sizeof *out);
            return MATCHER_ERR_NO_MEMORY;
        }
    }
    size_t *head = ame_calloc(T, sizeof *head);
    if (head == NULL) {
        for (size_t t = 0; t < T; t++)
            for (size_t i = 0; i < chunks[t].count; i++) match_result_free(&results[chunks[t].lo + i]);
        free(merged); free(chunks); free(results);
        memset(out, 0, sizeof *out);
        return MATCHER_ERR_NO_MEMORY;
    }
    for (size_t k = 0; k < cap; k++) {
        size_t best = T;
        for (size_t t = 0; t < T; t++) {
            if (head[t] == chunks[t].count) continue;
            if (best == T || result_cmp(&results[chunks[t].lo + head[t]],
                                        &results[chunks[best].lo + head[best]]) < 0) best = t;
        }
        merged[k] = results[chunks[best].lo + head[best]];
        head[best]++;
    }
    /* o que sobrou depois do top_k global */
    for (size_t t = 0; t < T; t++)
        for (size_t i = head[t]; i < chunks[t].count; i++) match_result_free(&results[chunks[t].lo + i]);
    free(head); free(chunks); free(results);
    const size_t cnt = cap;
    results = merged;
    out->status          = MATCH_STATUS_EVALUATED;
    out->evaluated_count = actor_count;
    out->passed_count    = passed;
    out->count           = cnt;
    out->results         = results;
    return MATCHER_OK;
}
