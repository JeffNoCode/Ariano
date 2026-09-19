#include <stdio.h>
#include <string.h>

#include "batch.h"
#include "matcher.h"
#include "report.h"

enum { T_AI = 1, T_PYTHON = 2, T_ML = 3, T_LLM = 4 };

int main(void)
{
    const Tag tags[] = {
        { T_AI, "AI" }, { T_PYTHON, "PYTHON" }, { T_ML, "MACHINE_LEARNING" }, { T_LLM, "LLM" }
    };
    const TagCatalog catalog = { tags, sizeof tags / sizeof tags[0] };

    const ActorTag actor_tags[] = { { T_AI, 0.9 }, { T_PYTHON, 0.9 }, { T_ML, 0.9 } };
    const Actor actor = { 42, ACTOR_TYPE_SOLVER, ACTOR_STATUS_ACTIVE,
                          actor_tags, sizeof actor_tags / sizeof actor_tags[0] };

    const DemandTag demand_tags[] = {
        { T_AI,     TAG_TYPE_REQUIRED,  1.0 },
        { T_PYTHON, TAG_TYPE_REQUIRED,  1.0 },
        { T_LLM,    TAG_TYPE_DESIRABLE, 1.0 }
    };
    const Demand demand = { 10, demand_tags, sizeof demand_tags / sizeof demand_tags[0] };

    /* MACHINE_LEARNING -> LLM (direcionada) */
    const TagRelationship rels[] = { { T_ML, T_LLM, RELATION_RELATED, 0.8 } };
    const RelationSet relations = { rels, sizeof rels / sizeof rels[0] };

    MatchResult result;
    MatcherError err = matcher_run(&actor, &demand, &relations, NULL, &result);
    if (err != MATCHER_OK) {
        fprintf(stderr, "matcher_run failed: %s\n", matcher_strerror(err));
        return 1;
    }
    match_result_print(stdout, &result, &catalog);
    match_result_free(&result);

    /* ---- Batch: 1 demanda x N atores -> ordenado, com threshold e top_k ---- */
    const ActorTag t_full[]  = { { T_AI, 1.0 }, { T_PYTHON, 1.0 }, { T_LLM, 1.0 } };
    const ActorTag t_core[]  = { { T_AI, 1.0 }, { T_PYTHON, 1.0 } };
    const ActorTag t_half[]  = { { T_AI, 1.0 } };
    const ActorTag t_other[] = { { T_LLM, 0.4 } };
    const Actor actors[] = {
        { 42, ACTOR_TYPE_SOLVER,  ACTOR_STATUS_ACTIVE, actor_tags, 3 },
        { 7,  ACTOR_TYPE_STARTUP, ACTOR_STATUS_ACTIVE, t_full,  3 },
        { 8,  ACTOR_TYPE_STARTUP, ACTOR_STATUS_ACTIVE, t_core,  2 },
        { 9,  ACTOR_TYPE_SOLVER,  ACTOR_STATUS_ACTIVE, t_half,  1 },
        { 11, ACTOR_TYPE_SOLVER,  ACTOR_STATUS_ACTIVE, t_other, 1 }
    };
    const BatchOptions opts = { .threshold = 0.30, .top_k = 3 };
    BatchResult batch;
    int64_t failed_id;
    err = batch_match(actors, sizeof actors / sizeof actors[0], &demand, &relations, NULL,
                      &opts, &batch, &failed_id);
    if (err != MATCHER_OK) {
        fprintf(stderr, "batch_match failed: %s (actor %lld)\n", matcher_strerror(err),
                (long long)failed_id);
        return 1;
    }
    printf("\nBatch: evaluated=%zu passed(threshold>=%.2f)=%zu returned(top_k=%zu)=%zu\n",
           batch.evaluated_count, opts.threshold, batch.passed_count, opts.top_k, batch.count);
    for (size_t i = 0; i < batch.count; i++) {
        const MatchResult *r = &batch.results[i];
        printf("  #%zu actor=%lld score=%.4f class=%s required_missing=%zu\n", i + 1,
               (long long)r->actor_id, r->score, match_class_name(r->match_class),
               r->required_missing_count);
    }
    batch_result_free(&batch);
    return 0;
}
