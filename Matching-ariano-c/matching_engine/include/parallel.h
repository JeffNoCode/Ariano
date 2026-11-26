/*
 * parallel.h - batch_match em varias threads (POSIX threads).
 *
 * Mesmo contrato e MESMO RESULTADO de batch_match(): mesmas validacoes, mesmos
 * erros, mesma ordenacao total e deterministica, mesmo threshold e top_k. A
 * unica diferenca e que os atores sao avaliados em `n_threads` threads.
 *
 * DIVISAO DO TRABALHO (deterministica, usada tambem pela interface):
 *   a thread t (0-based) avalia os atores do intervalo
 *       [ t * n / T , (t + 1) * n / T )        com T = threads efetivas
 *   T = min(n_threads, actor_count, PARALLEL_MAX_THREADS), no minimo 1.
 *
 * PROGRESSO: se `progress` nao for NULL, deve apontar para um array de pelo
 * menos `n_threads` posicoes; progress[t] recebe quantos atores a thread t ja
 * avaliou (escrita atomica relaxada, a cada PARALLEL_PROGRESS_STEP atores e no
 * fim). Outra thread pode ler esses valores enquanto o lote roda, para exibir
 * barras de progresso. O motor nunca le esse array.
 *
 * ERROS: se varios atores forem invalidos, o erro devolvido e o do ator de
 * MENOR indice - exatamente o que batch_match() devolveria.
 *
 * Seguro para chamar de varias threads ao mesmo tempo: o motor nao tem estado
 * global fora dos builds de teste (-DARIANO_TESTING).
 */
#ifndef ARIANO_PARALLEL_H
#define ARIANO_PARALLEL_H

#include "batch.h"

#define PARALLEL_MAX_THREADS  64
#define PARALLEL_PROGRESS_STEP 256

/* Quantas threads serao de fato usadas para `actor_count` atores. */
size_t parallel_effective_threads(size_t n_threads, size_t actor_count);

MatcherError batch_match_parallel(const Actor *actors, size_t actor_count,
                                  const Demand *demand, const RelationSet *relations,
                                  const MatchConfig *config, const BatchOptions *options,
                                  size_t n_threads, size_t *progress,
                                  BatchResult *out, int64_t *failed_actor_id);

#endif /* ARIANO_PARALLEL_H */
