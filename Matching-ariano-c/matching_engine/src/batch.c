#include "batch.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "alloc.h"

#define ID_UNKNOWN INT64_MIN
#define SCORE_SCALE 1e9


static int64_t score_key(double score)
{
    return (int64_t)llround(score * SCORE_SCALE);
}

static int result_cmp(const MatchResult *a, const MatchResult *b)
{
    int64_t ka = score_key(a->score), kb = score_key(b->score);
    if (ka != kb) {
        return (ka > kb) ? -1 : 1;
    }
    if (a->required_missing_count != b->required_missing_count) {
        return (a->required_missing_count < b->required_missing_count) ? -1 : 1;
    }
    if (a->actor_id != b->actor_id) {
        return (a->actor_id < b->actor_id) ? -1 : 1;
    }
    return 0;
}

static int qsort_result_cmp(const void *x, const void *y)
{
    return result_cmp((const MatchResult *)x, (const MatchResult *)y);
}

static int cmp_i64(const void *x, const void *y)
{
    int64_t a = *(const int64_t *)x, b = *(const int64_t *)y;
    return (a > b) - (a < b);
}

static MatcherError check_unique_actor_ids(const Actor *actors, size_t n, int64_t *dup_id)
{
    if (n < 2) {
        return MATCHER_OK;
    }
    int64_t *ids = ame_calloc(n, sizeof *ids);
    if (ids == NULL) {
        return MATCHER_ERR_NO_MEMORY;
    }
    for (size_t i = 0; i < n; i++) {
        ids[i] = actors[i].id;
    }
    qsort(ids, n, sizeof *ids, cmp_i64);
    MatcherError err = MATCHER_OK;
    for (size_t i = 1; i < n; i++) {
        if (ids[i] == ids[i - 1]) {
            *dup_id = ids[i];
            err = MATCHER_ERR_DUPLICATE_ACTOR;
            break;
        }
    }
    free(ids);
    return err;
}
static bool insert_bounded(MatchResult *arr, size_t *cnt, size_t cap, const MatchResult *cand)
{
    if (*cnt == cap && result_cmp(cand, &arr[cap - 1]) >= 0) {
        return false;
    }
    size_t lo = 0, hi = *cnt;
    while (lo < hi) {
        size_t mid = lo + (hi - lo) / 2;
        if (result_cmp(cand, &arr[mid]) < 0) {
            hi = mid;
        } else {
            lo = mid + 1;
        }
    }
    if (*cnt == cap) {
        match_result_free(&arr[cap - 1]);
        (*cnt)--;
    }
    memmove(&arr[lo + 1], &arr[lo], (*cnt - lo) * sizeof *arr);
    arr[lo] = *cand;
    (*cnt)++;
    return true;
}

BatchOptions batch_default_options(void)
{
    BatchOptions o = { .threshold = 0.0, .top_k = BATCH_TOP_K_UNLIMITED };
    return o;
}

MatcherError batch_match(const Actor *actors, size_t actor_count, const Demand *demand,
                         const RelationSet *relations, const MatchConfig *config,
                         const BatchOptions *options, BatchResult *out,
                         int64_t *failed_actor_id)
{
    if (failed_actor_id != NULL) {
        *failed_actor_id = ID_UNKNOWN;
    }
    if (out == NULL) {
        return MATCHER_ERR_NULL_ARG;
    }
    memset(out, 0, sizeof *out);
    if (demand == NULL || (actor_count > 0 && actors == NULL)) {
        return MATCHER_ERR_NULL_ARG;
    }
    if (relations != NULL && relations->count > 0 && relations->items == NULL) {
        return MATCHER_ERR_NULL_ARG;
    }

    const BatchOptions opt = (options != NULL) ? *options : batch_default_options();
    if (!isfinite(opt.threshold) || opt.threshold < 0.0 || opt.threshold > 1.0) {
        return MATCHER_ERR_INVALID_OPTIONS;
    }
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
    if (actor_count == 0) {
        return MATCHER_OK;
    }

    int64_t bad_id = ID_UNKNOWN;
    err = check_unique_actor_ids(actors, actor_count, &bad_id);
    if (err != MATCHER_OK) {
        memset(out, 0, sizeof *out);
        if (failed_actor_id != NULL) *failed_actor_id = bad_id;
        return err;
    }

    const bool   limited = (opt.top_k > 0 && opt.top_k < actor_count);
    const size_t cap     = limited ? opt.top_k : actor_count;
    const int64_t thr_key = score_key(opt.threshold);

    MatchResult *arr = ame_calloc(cap, sizeof *arr);
    if (arr == NULL) {
        memset(out, 0, sizeof *out);
        return MATCHER_ERR_NO_MEMORY;
    }

    size_t cnt = 0, evaluated = 0, passed = 0;
    for (size_t i = 0; i < actor_count; i++) {
        MatchResult r;
        err = matcher_run(&actors[i], demand, relations, &cfg, &r);
        if (err != MATCHER_OK) {
            bad_id = (err == MATCHER_ERR_NO_MEMORY) ? ID_UNKNOWN : actors[i].id;
            goto fail;
        }
        evaluated++;
        if (score_key(r.score) < thr_key) {
            match_result_free(&r);
            continue;
        }
        passed++;
        if (limited) {
            if (!insert_bounded(arr, &cnt, cap, &r)) {
                match_result_free(&r);
            }
        } else {
            arr[cnt++] = r;
        }
    }

    if (!limited && cnt > 1) {
        qsort(arr, cnt, sizeof *arr, qsort_result_cmp);
    }
    if (cnt == 0) {
        free(arr);
        arr = NULL;
    }
    out->status          = MATCH_STATUS_EVALUATED;
    out->evaluated_count = evaluated;
    out->passed_count    = passed;
    out->count           = cnt;
    out->results         = arr;
    return MATCHER_OK;

fail:
    for (size_t k = 0; k < cnt; k++) {
        match_result_free(&arr[k]);
    }
    free(arr);
    memset(out, 0, sizeof *out);
    if (failed_actor_id != NULL) *failed_actor_id = bad_id;
    return err;
}

void batch_result_free(BatchResult *result)
{
    if (result == NULL) {
        return;
    }
    for (size_t i = 0; i < result->count; i++) {
        match_result_free(&result->results[i]);
    }
    free(result->results);
    memset(result, 0, sizeof *result);
}
