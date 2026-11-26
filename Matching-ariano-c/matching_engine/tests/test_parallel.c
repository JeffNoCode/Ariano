/*
 * test_parallel.c - batch_match_parallel() tem de devolver EXATAMENTE o que
 * batch_match() devolve (mesmos atores, mesma ordem, mesmos scores e o mesmo
 * detalhe por tag), para qualquer numero de threads, threshold e top_k.
 *
 * Compilado sem -DARIANO_TESTING: a injecao de falhas de alocacao usa
 * contadores globais e nao e segura com varias threads.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "bench.h"
#include "parallel.h"

static int g_checks = 0, g_failed = 0;

#define CHECK(cond, ...) do { g_checks++; if (!(cond)) { g_failed++; \
    printf("  FALHOU (%s:%d): ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static uint64_t rng = 42;
static size_t rnd(size_t n)
{
    rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
    return (size_t)(rng % (uint64_t)n);
}

typedef struct { Actor *actors; ActorTag *tags; size_t n; } Pop;

static Pop make_pop(size_t n)
{
    Pop p = { calloc(n ? n : 1, sizeof(Actor)), calloc((n ? n : 1) * 6, sizeof(ActorTag)), n };
    for (size_t i = 0; i < n; i++) {
        ActorTag *t = &p.tags[i * 6];
        size_t k = 1 + rnd(6), used = 0;
        while (used < k) {
            int64_t id = (int64_t)(1 + rnd(12));
            int dup = 0;
            for (size_t j = 0; j < used; j++) if (t[j].tag_id == id) dup = 1;
            if (dup) continue;
            t[used].tag_id = id;
            t[used].weight = (double)rnd(5) * 0.25; /* inclui 0 e empates de score */
            used++;
        }
        /* ids embaralhados: a ordem de entrada nao pode influenciar a saida */
        p.actors[i] = (Actor){ .id = (int64_t)((i * 7919) % 1000003 + 1), .tags = t, .tag_count = k };
    }
    return p;
}

static void free_pop(Pop *p) { free(p->actors); free(p->tags); }

static int same_result(const MatchResult *a, const MatchResult *b)
{
    if (a->actor_id != b->actor_id || a->score != b->score || a->match_class != b->match_class ||
        a->required_score != b->required_score || a->desirable_score != b->desirable_score ||
        a->required_count != b->required_count || a->desirable_count != b->desirable_count ||
        a->required_missing_count != b->required_missing_count || a->status != b->status)
        return 0;
    size_t nd = a->required_count + a->desirable_count;
    for (size_t k = 0; k < nd; k++)
        if (memcmp(&a->details[k], &b->details[k], sizeof a->details[k]) != 0) return 0;
    return 1;
}

static void compare(const Pop *p, const Demand *d, const RelationSet *rel,
                    double threshold, size_t top_k, size_t threads)
{
    BatchOptions opt = { .threshold = threshold, .top_k = top_k };
    BatchResult seq, par;
    int64_t bad_s = 0, bad_p = 0;
    size_t progress[PARALLEL_MAX_THREADS] = { 0 };
    MatcherError es = batch_match(p->actors, p->n, d, rel, NULL, &opt, &seq, &bad_s);
    MatcherError ep = batch_match_parallel(p->actors, p->n, d, rel, NULL, &opt, threads, progress, &par, &bad_p);
    CHECK(es == ep, "erro diferente n=%zu T=%zu (%d x %d)", p->n, threads, es, ep);
    if (es != MATCHER_OK || ep != MATCHER_OK) {
        CHECK(bad_s == bad_p, "failed_actor_id diferente (%lld x %lld)", (long long)bad_s, (long long)bad_p);
        return;
    }
    CHECK(seq.count == par.count && seq.passed_count == par.passed_count &&
          seq.evaluated_count == par.evaluated_count && seq.status == par.status,
          "contagens diferentes n=%zu T=%zu thr=%.2f k=%zu", p->n, threads, threshold, top_k);
    size_t n = seq.count < par.count ? seq.count : par.count;
    int all_same = 1;
    for (size_t i = 0; i < n; i++) if (!same_result(&seq.results[i], &par.results[i])) { all_same = 0; break; }
    CHECK(all_same, "ranking diferente n=%zu T=%zu thr=%.2f k=%zu", p->n, threads, threshold, top_k);

    /* progresso: soma das fatias = todos os atores */
    size_t T = parallel_effective_threads(threads, p->n), sum = 0;
    for (size_t t = 0; t < T; t++) sum += progress[t];
    /* (demanda sem tags nao avalia ninguem: nao ha progresso a reportar) */
    CHECK(p->n == 0 || seq.status == MATCH_STATUS_NOT_EVALUABLE || sum == p->n,
          "progresso somou %zu, esperado %zu", sum, p->n);
    batch_result_free(&seq);
    batch_result_free(&par);
}

int main(void)
{
    const DemandTag dt[] = { { 1, TAG_TYPE_REQUIRED, 1.0 }, { 2, TAG_TYPE_REQUIRED, 2.0 },
                             { 3, TAG_TYPE_DESIRABLE, 1.0 } };
    const Demand demand = { .id = 9, .tags = dt, .tag_count = 3 };
    const TagRelationship rels[] = { { 5, 1, RELATION_RELATED, 0.8 }, { 6, 2, RELATION_SYNONYM, 0.5 },
                                     { 7, 2, RELATION_RELATED, 0.5 }, { 8, 3, RELATION_RELATED, 1.0 } };
    const RelationSet rel = { .items = rels, .count = 4 };

    const size_t sizes[]   = { 0, 1, 2, 7, 100, 1000, 25000 };
    const size_t threads[] = { 0, 1, 2, 3, 4, 8, 64, 200 };
    const double thrs[]    = { 0.0, 0.3, 1.0 };
    const size_t topks[]   = { 0, 1, 10, 100000 };

    printf("[ .. ] equivalencia sequencial x paralelo\n");
    for (size_t a = 0; a < sizeof sizes / sizeof *sizes; a++) {
        Pop p = make_pop(sizes[a]);
        for (size_t b = 0; b < sizeof threads / sizeof *threads; b++)
            for (size_t c = 0; c < sizeof thrs / sizeof *thrs; c++)
                for (size_t e = 0; e < sizeof topks / sizeof *topks; e++)
                    compare(&p, &demand, &rel, thrs[c], topks[e], threads[b]);
        free_pop(&p);
    }

    printf("[ .. ] erros: mesmo codigo e mesmo ator culpado\n");
    {
        Pop p = make_pop(5000);
        p.tags[4321 * 6].weight = 7.0;   /* peso invalido num trecho do fim */
        p.tags[1234 * 6].weight = -1.0;  /* e outro antes: este e o culpado */
        for (size_t b = 1; b <= 8; b++) compare(&p, &demand, &rel, 0.0, 0, b);
        free_pop(&p);
    }
    {
        Pop p = make_pop(3000);
        p.actors[2999].id = p.actors[10].id; /* id repetido */
        compare(&p, &demand, &rel, 0.0, 0, 4);
        free_pop(&p);
    }
    {
        Demand empty = { .id = 1, .tags = NULL, .tag_count = 0 };
        Pop p = make_pop(50);
        compare(&p, &empty, &rel, 0.0, 0, 4);
        free_pop(&p);
    }

    printf("[ .. ] base sintetica do benchmark: mesmo checksum com 1..8 threads\n");
    {
        BenchDataset *ds = bench_dataset_create(60000, 2026);
        CHECK(ds != NULL, "dataset nao criado");
        double ms; size_t passed0 = 0, passed; uint64_t sum0 = 0, sum;
        size_t progress[PARALLEL_MAX_THREADS];
        for (size_t t = 1; t <= 8; t++) {
            CHECK(bench_run(ds, t, progress, &ms, &passed, &sum) == MATCHER_OK, "bench_run falhou T=%zu", t);
            if (t == 1) { sum0 = sum; passed0 = passed; }
            CHECK(sum == sum0 && passed == passed0, "checksum diferente com T=%zu", t);
        }
        CHECK(bench_dataset_create(0, 1) == NULL, "dataset vazio deveria ser NULL");
        bench_dataset_free(ds);
        bench_dataset_free(NULL);
    }

    printf("\n%d checks, %d failed\n", g_checks, g_failed);
    return g_failed == 0 ? 0 : 1;
}
