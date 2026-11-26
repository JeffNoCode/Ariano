/*
 * bench.h - base sintetica para medir sequencial x paralelo.
 *
 * Gera, dentro do proprio C, uma base deterministica de N atores (a partir de
 * uma semente), uma demanda com 3 competencias obrigatorias e 2 desejaveis e
 * um conjunto de relacoes entre tags. Assim o tempo medido e so o do motor,
 * sem o custo de montar centenas de milhares de structs pela ponte Python.
 *
 * bench_run() roda batch_match_parallel() com `n_threads` e devolve o tempo
 * (relogio de parede), quantos atores passaram do threshold e um checksum do
 * ranking final (actor_id + score, na ordem). Mesmo checksum com 1 e com N
 * threads = mesmo ranking, ator por ator.
 */
#ifndef ARIANO_BENCH_H
#define ARIANO_BENCH_H

#include <stdint.h>

#include "parallel.h"

#define BENCH_MAX_ACTORS 2000000
#define BENCH_TOP_K      100

typedef struct BenchDataset BenchDataset;

/* NULL se n_actors for 0, maior que BENCH_MAX_ACTORS, ou faltar memoria. */
BenchDataset *bench_dataset_create(size_t n_actors, uint64_t seed);
void          bench_dataset_free(BenchDataset *ds);
size_t        bench_dataset_size(const BenchDataset *ds);

MatcherError bench_run(const BenchDataset *ds, size_t n_threads, size_t *progress,
                       double *elapsed_ms, size_t *passed_count, uint64_t *checksum);

#endif /* ARIANO_BENCH_H */
