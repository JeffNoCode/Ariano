# ARIANO — C Matching Engine (`mvp-1`)

Núcleo algorítmico do matching **ator × demanda**, isolado de banco, Python e I/O.
C17, sem dependências externas (só libc/libm).

```
make            # compila o demo    -> build/ariano_demo
make test       # testes com ASan + UBSan + LeakSanitizer (+ injeção de falha de alocação)
make valgrind   # opcional, se valgrind estiver instalado
```

## Estrutura

```
include/domain.h   enums + structs de domínio e regras de ownership
include/matcher.h  matcher_run (1 ator × 1 demanda), MatchConfig, validadores
include/batch.h    batch_match (1 demanda × N atores): threshold, ordenação, top_k
include/parallel.h batch_match_parallel: mesmo resultado de batch_match, em N pthreads
include/bench.h    base sintética determinística + medição de tempo (página Desempenho)
include/report.h   impressão legível (depuração)
include/alloc.h    (interno) wrapper de calloc com injeção de falha nos testes
src/               domain.c matcher.c batch.c parallel.c bench.c report.c alloc.c
                   main.c (demo) bench_main.c (make bench)
tests/             test_matcher.c (sequencial) test_parallel.c (paralelo == sequencial)
```

`make test` roda a suíte original, a de equivalência do paralelo (ASan/UBSan) e
a mesma sob ThreadSanitizer. `make bench` mede 1, 2, 4 e 8 threads. Detalhes,
números e a Lei de Amdahl aplicada: [docs/PARALELISMO.md](../../docs/PARALELISMO.md).

## 1. Semântica das relações (`source → target`)

> **Possuir a `source_tag` fornece evidência de compatibilidade com a `target_tag`.**

`MACHINE_LEARNING → LLM` significa: um ator que **possui** `MACHINE_LEARNING` pode atender uma demanda
que **exige** `LLM`. A relação é **direcionada**: com `LLM → MACHINE_LEARNING` no banco e demanda de `LLM`,
o ator que só tem `MACHINE_LEARNING` continua `MISSING`.

## 2. SYNONYM

`SYNONYM` é **direcional**, exatamente como `RELATED` (mesmo efeito no score; o tipo aparece em
`MatchDetail.relation_type`). O motor **não cria relações reversas**. Equivalência nos dois sentidos exige
os dois cadastros (`A → B` e `B → A`). `PART_OF` é ignorado (reservado). Não há fechamento transitivo.

## 3. Fórmula

```
coverage_i = actor_weight_i × relation_weight_i          (EXACT: relation_weight = 1)
G(grupo)   = Σ demand_weight_i × coverage_i / Σ demand_weight_i

R = G(REQUIRED)     D = G(DESIRABLE)     s = desirable_share (padrão 0.20)

score = R × ((1 − s) + s × D)     se há REQUIRED e DESIRABLE
      = R                         se só há REQUIRED
      = D                         se só há DESIRABLE
```

Escala **0.0–1.0** (`double`). Propriedades (todas cobertas por teste):
`0 ≤ score ≤ R ≤ 1`; monotônico nas coberturas; DESIRABLE nunca compensa REQUIRED ausente;
tags extras do ator não mudam o score (bit a bit); adicionar à demanda uma tag **sem cobertura** nunca
aumenta o score; só sobe se a nova tag for melhor coberta que a média atual (evidência real, não inflação).

**Fato de projeto:** com `s = 0.2`, uma demanda que tem DESIRABLE limita a 0.8 quem não atende nenhuma delas;
uma demanda só com REQUIRED chega a 1.0. Isso é intencional e só faz sentido comparar scores **dentro da
mesma demanda** (é o que o batch faz).

## 4. Os três pesos (cada um tem um único papel)

| Peso | Significado | Faixa |
|---|---|---|
| `actor_tag.weight` | **força** da competência do ator | [0, 1] |
| `relation.weight` | quanto a competência `source` **transfere** evidência para `target` | [0, 1] |
| `demand_tag.weight` | **importância** da tag na demanda (só normaliza; invariante a escala) | > 0 e soma finita |

**Regra de evidência:** um item só é `EXACT`/`RELATED` se `coverage > 0`. Peso 0 (do ator ou da relação)
= "declarado, sem evidência" ⇒ não cobre. Invariante: `MISSING ⇔ coverage == 0`.
`demand_weight = 0` é **rejeitado** (`INVALID_WEIGHT`): não há divisão por zero; um peso 0 seria uma tag
sem efeito, que deve ser removida da demanda. Pesos que somam `inf` também são rejeitados (evita `NaN`).

## 5. Estado por item — `MatchType`

| Valor | Significado |
|---|---|
| `EXACT` | o ator possui a própria tag (coverage = `actor_weight`). Tem precedência sobre relações. |
| `RELATED` | coberto por relação `source → target` com `source` em posse do ator. Vale a **melhor** relação (nunca soma). Desempate: maior cobertura → menor id de origem → SYNONYM antes de RELATED. |
| `MISSING` | avaliou e **não há evidência** (sem tag, sem relação válida, ou coverage 0). |

## 6. Classificação global — `MatchClass` (vai para `tb_matches.match_type`)

Calculada sobre o grupo **REQUIRED** (sobre DESIRABLE só se a demanda não tem REQUIRED).
Precedência: **completude primeiro, exatidão depois**.

| Situação nos itens do grupo | Classe |
|---|---|
| todos `EXACT` | `EXACT` |
| todos cobertos, ao menos um `RELATED` | `RELATED` |
| alguns cobertos e algum `MISSING` (mesmo que haja RELATED) | `PARTIAL` |
| todos `MISSING` | `NONE` |

A classe descreve o **tipo** da cobertura, não a **força**: ator com `actor_weight = 0.1` em todas as REQUIRED é
`EXACT` com score 0.1. DESIRABLE não altera a classe (não é "exigência"); o score já a reflete.

## 7. `MatchStatus`

`EVALUATED` — calculado (inclusive quando tudo é `MISSING`). `NOT_EVALUABLE` — demanda **sem nenhuma tag**:
não há o que casar; score 0, sem `details`; **não deve ser persistido como match**. (No batch: 0 resultados.)

## 8. `desirable_share` (`MatchConfig`)

Em [0, 1], padrão 0.20. `0` → `score = R`. `1` → `score = R × D` (DESIRABLE vira multiplicador total: sem
nenhuma DESIRABLE o score é 0). Sem REQUIRED ou sem DESIRABLE, `s` é irrelevante.

## Batch: `batch_match(actors, n, demand, relations, config, options, out, failed_actor_id)`

```
1 Demand + N Actors → N MatchResult → threshold → ordenação → top_k → BatchResult
```

- **9. threshold** (`BatchOptions.threshold`, em [0,1]): mantém `score >= threshold` (inclusivo). É só filtro:
  não altera scores. `0` mantém todos, inclusive score 0.
- **10. top_k** (`BatchOptions.top_k`): máximo de resultados, aplicado **após** threshold e ordenação.
  **`0` = sem limite** (`BATCH_TOP_K_UNLIMITED`). `passed_count` conta os aprovados no threshold **antes** do corte.
- **11. ordenação determinística** (total; independe da ordem de entrada):
  1. maior `score`; 2. menor `required_missing_count`; 3. menor `actor_id`.
  `actor_id` deve ser único no lote (senão `MATCHER_ERR_DUPLICATE_ACTOR`).
  Scores são comparados com resolução de **1e-9** (chave inteira), para que ruído de ponto flutuante
  (ex.: média que deveria ser 0.3 sai `0.29999999999999993`) não exclua um ator do threshold nem quebre empates.
  O `score` armazenado no resultado **não** é arredondado.
- **12. `required_missing_count`** é preservado em cada `MatchResult`. O batch **não** exclui por
  `required_missing_count > 0` nem por `ActorStatus`: é decisão de negócio do chamador
  (ex.: filtrar `required_missing_count == 0` depois).
- **Erros:** falha rápida — um ator com dado inválido derruba o lote (`failed_actor_id` identifica o ator);
  nenhum resultado parcial. Demanda inválida é detectada mesmo com 0 atores.

### Ownership e memória

- Entradas (`Actor`, `Demand`, `RelationSet`, configs, options) são **views somente-leitura**; nunca alteradas
  nem retidas (testado com cópias + `memcmp`, inclusive a ordem do array de atores).
- `BatchResult` **é dono** de `results` e de cada `results[i].details`. Liberar **somente** com
  `batch_result_free()` (idempotente, aceita `NULL`). Em erro, nada a liberar.
- `top_k < N`: vetor de capacidade `top_k` mantido ordenado por inserção; nunca mais de `top_k + 1` resultados vivos.
  `top_k` ilimitado: vetor de capacidade N + `qsort`. Alocações via `calloc` (proteção de overflow).
- Os testes injetam falha em **cada** alocação possível (`-DARIANO_TESTING`) e verificam `NO_MEMORY` sem vazamento.

## 13. Limitações atuais

- Busca linear: custo ≈ O(N × D × (R + A)); sem índices. Medir antes de otimizar.
- `matcher_run` revalida a demanda a cada ator (custo O(D²) por ator, redundante no batch).
- Sem transitividade nem lógica de `PART_OF`; SYNONYM não é simétrico.
- O vetor do modo ilimitado tem capacidade N mesmo se poucos passarem no threshold.
- Scores só são comparáveis dentro da mesma demanda (a forma da demanda define o teto).
- Valores de `ActorStatus` são provisórios; o motor não filtra por status/tipo.

## Decisões em aberto

1. Confirmar `actor_weight = 0` e `relation_weight = 0` como "sem evidência" (adotado nesta etapa).
2. `desirable_share` padrão 0.20 e `top_k = 0` = ilimitado.
3. Batch: falha rápida (adotado) vs. pular o ator inválido e reportar.
4. Threshold mínimo de negócio / exclusão por REQUIRED ausente: fica com o chamador.
