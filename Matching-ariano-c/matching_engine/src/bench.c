#include "bench.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "alloc.h"

#define BENCH_TAG_UNIVERSE 60   /* tags 1..60 */
#define BENCH_MIN_TAGS     4
#define BENCH_MAX_TAGS     8

struct BenchDataset {
    size_t           n;
    Actor           *actors;
    ActorTag        *tags;      /* um bloco so; cada ator aponta para sua fatia */
    DemandTag        demand_tags[5];
    Demand           demand;
    TagRelationship *relations;
    RelationSet      relation_set;
};

/* splitmix64: gerador pequeno, rapido e deterministico (mesma base em qualquer maquina). */
static uint64_t next_u64(uint64_t *s)
{
    uint64_t z = (*s += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

static size_t rand_below(uint64_t *s, size_t n)
{
    return (size_t)(next_u64(s) % (uint64_t)n);
}

BenchDataset *bench_dataset_create(size_t n_actors, uint64_t seed)
{
    if (n_actors == 0 || n_actors > BENCH_MAX_ACTORS) return NULL;
    BenchDataset *ds = ame_calloc(1, sizeof *ds);
    if (ds == NULL) return NULL;
    ds->n = n_actors;
    ds->actors = ame_calloc(n_actors, sizeof *ds->actors);
    ds->tags = ame_calloc(n_actors * BENCH_MAX_TAGS, sizeof *ds->tags);
    const size_t n_rel = 30;
    ds->relations = ame_calloc(n_rel, sizeof *ds->relations);
    if (!ds->actors || !ds->tags || !ds->relations) {
        bench_dataset_free(ds);
        return NULL;
    }

    uint64_t s = seed;
    for (size_t i = 0; i < n_actors; i++) {
        ActorTag *mine = &ds->tags[i * BENCH_MAX_TAGS];
        size_t k = BENCH_MIN_TAGS + rand_below(&s, BENCH_MAX_TAGS - BENCH_MIN_TAGS + 1);
        size_t used = 0;
        while (used < k) {
            int64_t tag = (int64_t)(1 + rand_below(&s, BENCH_TAG_UNIVERSE));
            int dup = 0;
            for (size_t j = 0; j < used; j++) if (mine[j].tag_id == tag) { dup = 1; break; }
            if (dup) continue;
            mine[used].tag_id = tag;
            mine[used].weight = (double)(2 + rand_below(&s, 19)) * 0.05; /* 0,10 .. 1,00 */
            used++;
        }
        ds->actors[i] = (Actor){ .id = (int64_t)(i + 1), .type = ACTOR_TYPE_STARTUP,
                                 .status = ACTOR_STATUS_ACTIVE, .tags = mine, .tag_count = k };
    }

    /* Demanda: tags 1,2,3 obrigatorias; 4,5 desejaveis. */
    const DemandTag dt[5] = {
        { 1, TAG_TYPE_REQUIRED, 1.0 }, { 2, TAG_TYPE_REQUIRED, 1.0 }, { 3, TAG_TYPE_REQUIRED, 0.5 },
        { 4, TAG_TYPE_DESIRABLE, 1.0 }, { 5, TAG_TYPE_DESIRABLE, 1.0 },
    };
    memcpy(ds->demand_tags, dt, sizeof dt);
    ds->demand = (Demand){ .id = 1, .tags = ds->demand_tags, .tag_count = 5 };

    /* Relacoes: tags 6..35 dao evidencia parcial para alguma das tags 1..5. */
    for (size_t r = 0; r < n_rel; r++) {
        ds->relations[r] = (TagRelationship){
            .source_tag_id = (int64_t)(6 + r),
            .target_tag_id = (int64_t)(1 + r % 5),
            .type = (r % 4 == 0) ? RELATION_SYNONYM : RELATION_RELATED,
            .weight = 0.5 + 0.1 * (double)(r % 5),
        };
    }
    ds->relation_set = (RelationSet){ .items = ds->relations, .count = n_rel };
    return ds;
}

void bench_dataset_free(BenchDataset *ds)
{
    if (ds == NULL) return;
    free(ds->actors);
    free(ds->tags);
    free(ds->relations);
    free(ds);
}

size_t bench_dataset_size(const BenchDataset *ds)
{
    return ds ? ds->n : 0;
}

static double now_ms(void)
{
    struct timespec ts;
    timespec_get(&ts, TIME_UTC);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1e6;
}

MatcherError bench_run(const BenchDataset *ds, size_t n_threads, size_t *progress,
                       double *elapsed_ms, size_t *passed_count, uint64_t *checksum)
{
    if (ds == NULL || elapsed_ms == NULL || passed_count == NULL || checksum == NULL)
        return MATCHER_ERR_NULL_ARG;

    const BatchOptions opt = { .threshold = 0.0, .top_k = BENCH_TOP_K };
    BatchResult out;
    int64_t bad = 0;
    double t0 = now_ms();
    MatcherError err = batch_match_parallel(ds->actors, ds->n, &ds->demand, &ds->relation_set,
                                            NULL, &opt, n_threads, progress, &out, &bad);
    *elapsed_ms = now_ms() - t0;
    if (err != MATCHER_OK) return err;

    /* FNV-1a sobre (actor_id, score em 1e-9) na ordem do ranking. */
    uint64_t h = 0xCBF29CE484222325ULL;
    for (size_t i = 0; i < out.count; i++) {
        int64_t parts[2] = { out.results[i].actor_id, (int64_t)llround(out.results[i].score * 1e9) };
        const unsigned char *p = (const unsigned char *)parts;
        for (size_t b = 0; b < sizeof parts; b++) { h ^= p[b]; h *= 0x100000001B3ULL; }
    }
    *checksum = h;
    *passed_count = out.passed_count;
    batch_result_free(&out);
    return MATCHER_OK;
}
