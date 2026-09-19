/*
 * alloc.h - Ponto unico de alocacao do motor (uso interno).
 *
 * Em builds normais e apenas um wrapper de calloc. Em builds de teste
 * (-DARIANO_TESTING) permite fazer a N-esima alocacao falhar, para exercitar
 * os caminhos de NO_MEMORY e provar (via ASan/LSan) que nao ha vazamento neles.
 */
#ifndef ARIANO_ALLOC_H
#define ARIANO_ALLOC_H

#include <stddef.h>

/* calloc(n, size) com checagem de overflow (herdada do calloc). NULL em falha. */
void *ame_calloc(size_t n, size_t size);

#ifdef ARIANO_TESTING
/* A alocacao de numero `n` (1-based, contada a partir desta chamada) retorna NULL.
 * n = 0 desativa a injecao. Zera o contador. */
void ame_test_fail_nth_alloc(long n);
/* Quantas alocacoes foram pedidas desde a ultima chamada de ame_test_fail_nth_alloc. */
long ame_test_alloc_count(void);
#endif

#endif /* ARIANO_ALLOC_H */
