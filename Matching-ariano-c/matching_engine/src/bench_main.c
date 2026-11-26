/*
 * bench_main.c - `make bench`: tempo do motor com 1, 2, 4 e 8 threads.
 *
 *   ./build/ariano_bench [atores] [repeticoes]      (padrao: 200000 3)
 *
 * Para cada numero de threads usa a MELHOR de N repeticoes (menos ruido) e
 * confere que o checksum do ranking e o mesmo da execucao com 1 thread.
 */
#include <stdio.h>
#include <stdlib.h>

#include "bench.h"

int main(int argc, char **argv)
{
    size_t n = argc > 1 ? (size_t)strtoull(argv[1], NULL, 10) : 200000;
    int reps = argc > 2 ? atoi(argv[2]) : 3;
    if (reps < 1) reps = 1;

    BenchDataset *ds = bench_dataset_create(n, 2026);
    if (ds == NULL) {
        fprintf(stderr, "nao foi possivel gerar a base (1..%d atores)\n", BENCH_MAX_ACTORS);
        return 1;
    }
    printf("ARIANO bench | %zu atores | melhor de %d repeticoes\n\n", n, reps);
    printf("threads   tempo (ms)   speedup   ranking\n");

    const size_t ts[] = { 1, 2, 4, 8 };
    double base = 0.0;
    uint64_t base_sum = 0;
    size_t progress[PARALLEL_MAX_THREADS];
    for (size_t k = 0; k < sizeof ts / sizeof *ts; k++) {
        double best = 0.0;
        uint64_t sum = 0;
        size_t passed = 0;
        for (int r = 0; r < reps; r++) {
            double ms;
            if (bench_run(ds, ts[k], progress, &ms, &passed, &sum) != MATCHER_OK) {
                fprintf(stderr, "falha no motor\n");
                bench_dataset_free(ds);
                return 1;
            }
            if (r == 0 || ms < best) best = ms;
        }
        if (k == 0) { base = best; base_sum = sum; }
        printf("%7zu   %10.1f   %6.2fx   %s\n", ts[k], best, base / best,
               sum == base_sum ? "identico" : "DIFERENTE!");
    }
    bench_dataset_free(ds);
    return 0;
}
