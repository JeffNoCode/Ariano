#include <math.h>
#include <stdio.h>
#include <string.h>

#include <stdint.h>

#include "alloc.h"
#include "batch.h"
#include "matcher.h"
#include "report.h"

static int g_checks = 0;
static int g_failed = 0;

#define CHECK(cond)                                                              \
    do {                                                                         \
        g_checks++;                                                              \
        if (!(cond)) {                                                           \
            g_failed++;                                                          \
            fprintf(stderr, "    FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);  \
        }                                                                        \
    } while (0)

#define CHECK_NEAR(a, b) CHECK(fabs((double)(a) - (double)(b)) < 1e-9)

#define RUN(fn)                                                                  \
    do {                                                                         \
        int before = g_failed;                                                   \
        fn();                                                                    \
        printf("[%s] %s\n", g_failed == before ? " OK " : "FAIL", #fn);          \
    } while (0)

#define N(arr) (sizeof(arr) / sizeof((arr)[0]))

enum { AI = 1, PYTHON = 2, ML = 3, LLM = 4, JAVA = 5, SPRING = 6, DOCKER = 7, K8S = 8, DL = 9 };

#define REQ(id, w) { (id), TAG_TYPE_REQUIRED, (w) }
#define DES(id, w) { (id), TAG_TYPE_DESIRABLE, (w) }
#define REL(src, dst, type, w) { (src), (dst), (type), (w) }

static Actor mk_actor(const ActorTag *t, size_t n)
{
    Actor a = { 42, ACTOR_TYPE_SOLVER, ACTOR_STATUS_ACTIVE, t, n };
    return a;
}

static Demand mk_demand(const DemandTag *t, size_t n)
{
    Demand d = { 10, t, n };
    return d;
}

static RelationSet mk_rels(const TagRelationship *r, size_t n)
{
    RelationSet s = { r, n };
    return s;
}

static MatchResult run_ok(const Actor *a, const Demand *d, const RelationSet *r)
{
    MatchResult res;
    MatcherError e = matcher_run(a, d, r, NULL, &res);
    CHECK(e == MATCHER_OK);
    return res;
}

static void expect_err(const Actor *a, const Demand *d, const RelationSet *r,
                       const MatchConfig *c, MatcherError want)
{
    MatchResult res;
    MatcherError e = matcher_run(a, d, r, c, &res);
    CHECK(e == want);
    CHECK(res.details == NULL);
    CHECK(res.score == 0.0);
    match_result_free(&res);
}


/* T1 - todas as REQUIRED sao EXACT */
static void test_01_all_required_exact(void)
{
    ActorTag at[] = { { AI, 1.0 }, { PYTHON, 1.0 } };
    DemandTag dt[] = { REQ(AI, 1.0), REQ(PYTHON, 1.0) };
    Actor a = mk_actor(at, N(at));
    Demand d = mk_demand(dt, N(dt));
    MatchResult r = run_ok(&a, &d, NULL);

    CHECK(r.status == MATCH_STATUS_EVALUATED);
    CHECK_NEAR(r.score, 1.0);
    CHECK(r.match_class == MATCH_CLASS_EXACT);
    CHECK(r.required_count == 2 && r.desirable_count == 0);
    CHECK(r.required_missing_count == 0);
    CHECK(match_result_required(&r)[0].match == MATCH_EXACT);
    CHECK(match_result_required(&r)[1].match == MATCH_EXACT);
    match_result_free(&r);
}

/* T2 - algumas REQUIRED EXACT, outras MISSING */
static void test_02_some_required_missing(void)
{
    ActorTag at[] = { { AI, 1.0 } };
    DemandTag dt[] = { REQ(AI, 1.0), REQ(PYTHON, 1.0) };
    Actor a = mk_actor(at, N(at));
    Demand d = mk_demand(dt, N(dt));
    MatchResult r = run_ok(&a, &d, NULL);

    CHECK_NEAR(r.score, 0.5);
    CHECK(r.match_class == MATCH_CLASS_PARTIAL);
    CHECK(r.required_missing_count == 1);
    const MatchDetail *req = match_result_required(&r);
    CHECK(req[0].match == MATCH_EXACT);
    CHECK(req[1].match == MATCH_MISSING);
    CHECK(req[1].actor_tag_id == TAG_ID_NONE);
    CHECK(req[1].relation_type == RELATION_NONE);
    CHECK_NEAR(req[1].coverage, 0.0);
    match_result_free(&r);
}

/* T3 - REQUIRED coberta por RELATED */
static void test_03_required_related(void)
{
    ActorTag at[] = { { ML, 1.0 } };
    DemandTag dt[] = { REQ(LLM, 1.0) };
    TagRelationship rl[] = { REL(ML, LLM, RELATION_RELATED, 0.8) };
    Actor a = mk_actor(at, N(at));
    Demand d = mk_demand(dt, N(dt));
    RelationSet rs = mk_rels(rl, N(rl));
    MatchResult r = run_ok(&a, &d, &rs);

    CHECK_NEAR(r.score, 0.8);
    CHECK(r.match_class == MATCH_CLASS_RELATED);
    const MatchDetail *x = match_result_required(&r);
    CHECK(x[0].match == MATCH_RELATED);
    CHECK(x[0].actor_tag_id == ML);
    CHECK(x[0].relation_type == RELATION_RELATED);
    CHECK_NEAR(x[0].relation_weight, 0.8);
    CHECK(r.required_missing_count == 0);
    match_result_free(&r);
}

/* T4 - DESIRABLE coberta por RELATED (cenario do enunciado) */
static void test_04_desirable_related(void)
{
    DemandTag dt[] = { REQ(AI, 1.0), REQ(PYTHON, 1.0), DES(LLM, 1.0) };
    TagRelationship rl[] = { REL(ML, LLM, RELATION_RELATED, 0.8) };
    Demand d = mk_demand(dt, N(dt));
    RelationSet rs = mk_rels(rl, N(rl));

    ActorTag at1[] = { { AI, 1.0 }, { PYTHON, 1.0 }, { ML, 1.0 } };
    Actor a1 = mk_actor(at1, N(at1));
    MatchResult r1 = run_ok(&a1, &d, &rs);
    CHECK_NEAR(r1.required_score, 1.0);
    CHECK_NEAR(r1.desirable_score, 0.8);
    CHECK_NEAR(r1.score, 0.96);
    CHECK(r1.match_class == MATCH_CLASS_EXACT);
    CHECK(r1.required_count == 2 && r1.desirable_count == 1);
    CHECK(match_result_desirable(&r1)[0].match == MATCH_RELATED);
    CHECK(match_result_desirable(&r1)[0].actor_tag_id == ML);
    match_result_free(&r1);

    ActorTag at2[] = { { AI, 0.9 }, { PYTHON, 0.9 }, { ML, 0.9 } };
    Actor a2 = mk_actor(at2, N(at2));
    MatchResult r2 = run_ok(&a2, &d, &rs);
    CHECK_NEAR(r2.score, 0.9 * (0.8 + 0.2 * 0.72)); 
    match_result_free(&r2);
}

/* T5 - nenhuma tag corresponde */
static void test_05_nothing_matches(void)
{
    ActorTag at[] = { { JAVA, 1.0 } };
    DemandTag dt[] = { REQ(AI, 1.0), REQ(PYTHON, 1.0), DES(LLM, 1.0) };
    Actor a = mk_actor(at, N(at));
    Demand d = mk_demand(dt, N(dt));
    MatchResult r = run_ok(&a, &d, NULL);

    CHECK_NEAR(r.score, 0.0);
    CHECK(r.match_class == MATCH_CLASS_NONE);
    CHECK(r.status == MATCH_STATUS_EVALUATED); 
    CHECK(r.required_missing_count == 2);
    match_result_free(&r);
}

/* T6 - tags extras do ator nao alteram o score */
static void test_06_extra_actor_tags_ignored(void)
{
    DemandTag dt[] = { REQ(AI, 1.0), REQ(PYTHON, 1.0), DES(DOCKER, 1.0) };
    Demand d = mk_demand(dt, N(dt));

    ActorTag base[] = { { AI, 1.0 }, { PYTHON, 0.7 } };
    ActorTag extra[] = { { AI, 1.0 }, { PYTHON, 0.7 }, { JAVA, 1.0 }, { SPRING, 1.0 },
                         { K8S, 1.0 }, { ML, 1.0 }, { DL, 1.0 } };
    Actor a1 = mk_actor(base, N(base));
    Actor a2 = mk_actor(extra, N(extra));
    MatchResult r1 = run_ok(&a1, &d, NULL);
    MatchResult r2 = run_ok(&a2, &d, NULL);

    CHECK_NEAR(r1.score, r2.score);
    CHECK(r1.required_count == r2.required_count && r1.desirable_count == r2.desirable_count);
    match_result_free(&r1);
    match_result_free(&r2);
}

/* T7 - peso da tag do ator */
static void test_07_actor_tag_weight(void)
{
    DemandTag dt[] = { REQ(AI, 1.0), REQ(PYTHON, 1.0) };
    Demand d = mk_demand(dt, N(dt));

    ActorTag low[] = { { AI, 0.5 }, { PYTHON, 0.5 } };
    Actor a1 = mk_actor(low, N(low));
    MatchResult r1 = run_ok(&a1, &d, NULL);
    CHECK_NEAR(r1.score, 0.5);
    CHECK(r1.match_class == MATCH_CLASS_EXACT);
    match_result_free(&r1);

    ActorTag mix[] = { { AI, 0.5 }, { PYTHON, 1.0 } };
    Actor a2 = mk_actor(mix, N(mix));
    MatchResult r2 = run_ok(&a2, &d, NULL);
    CHECK_NEAR(r2.score, 0.75);
    match_result_free(&r2);
}

/* T8 - peso da tag da demanda (importancia relativa, invariante a escala) */
static void test_08_demand_tag_weight(void)
{
    DemandTag dt[] = { REQ(AI, 0.75), REQ(PYTHON, 0.25) };
    Demand d = mk_demand(dt, N(dt));
    ActorTag only_ai[] = { { AI, 1.0 } };
    ActorTag only_py[] = { { PYTHON, 1.0 } };
    Actor a1 = mk_actor(only_ai, 1), a2 = mk_actor(only_py, 1);
    MatchResult r1 = run_ok(&a1, &d, NULL), r2 = run_ok(&a2, &d, NULL);
    CHECK_NEAR(r1.score, 0.75);
    CHECK_NEAR(r2.score, 0.25);
    match_result_free(&r1);
    match_result_free(&r2);

    DemandTag scaled[] = { REQ(AI, 3.0), REQ(PYTHON, 1.0) }; 
    Demand ds = mk_demand(scaled, N(scaled));
    MatchResult r3 = run_ok(&a1, &ds, NULL);
    CHECK_NEAR(r3.score, 0.75);
    match_result_free(&r3);
}

/* T9 - peso da relacao; e o peso da demanda nao e contado duas vezes */
static void test_09_relation_weight(void)
{
    ActorTag at[] = { { ML, 0.9 } };
    Actor a = mk_actor(at, N(at));
    DemandTag dt[] = { REQ(LLM, 1.0) };
    Demand d = mk_demand(dt, N(dt));

    TagRelationship hi[] = { REL(ML, LLM, RELATION_RELATED, 0.8) };
    TagRelationship lo[] = { REL(ML, LLM, RELATION_RELATED, 0.4) };
    RelationSet rhi = mk_rels(hi, 1), rlo = mk_rels(lo, 1);
    MatchResult r1 = run_ok(&a, &d, &rhi), r2 = run_ok(&a, &d, &rlo);
    CHECK_NEAR(r1.score, 0.9 * 0.8);
    CHECK_NEAR(r2.score, 0.9 * 0.4);
    CHECK_NEAR(match_result_required(&r1)[0].coverage, 0.72);
    match_result_free(&r1);
    match_result_free(&r2);

    DemandTag half[] = { REQ(LLM, 0.5) };
    Demand dh = mk_demand(half, 1);
    MatchResult r3 = run_ok(&a, &dh, &rhi);
    CHECK_NEAR(r3.score, 0.72);
    match_result_free(&r3);
}

/* T10 - somente REQUIRED */
static void test_10_only_required(void)
{
    ActorTag at[] = { { JAVA, 1.0 }, { SPRING, 1.0 } };
    DemandTag dt[] = { REQ(JAVA, 1.0), REQ(SPRING, 1.0) };
    Actor a = mk_actor(at, N(at));
    Demand d = mk_demand(dt, N(dt));
    MatchResult r = run_ok(&a, &d, NULL);
    CHECK_NEAR(r.score, 1.0);
    CHECK(r.desirable_count == 0 && match_result_desirable(&r) == NULL);
    CHECK_NEAR(r.desirable_score, 0.0);
    match_result_free(&r);
}

/* T11 - somente DESIRABLE (nao ha "piso" de 0.8) */
static void test_11_only_desirable(void)
{
    DemandTag dt[] = { DES(DOCKER, 1.0), DES(K8S, 1.0) };
    Demand d = mk_demand(dt, N(dt));

    ActorTag none[] = { { JAVA, 1.0 } };
    Actor a0 = mk_actor(none, 1);
    MatchResult r0 = run_ok(&a0, &d, NULL);
    CHECK_NEAR(r0.score, 0.0);
    CHECK(r0.match_class == MATCH_CLASS_NONE);
    CHECK(r0.required_count == 0 && r0.desirable_count == 2);
    match_result_free(&r0);

    ActorTag one[] = { { DOCKER, 1.0 } };
    Actor a1 = mk_actor(one, 1);
    MatchResult r1 = run_ok(&a1, &d, NULL);
    CHECK_NEAR(r1.score, 0.5);
    CHECK(r1.match_class == MATCH_CLASS_PARTIAL);
    match_result_free(&r1);

    ActorTag both[] = { { DOCKER, 1.0 }, { K8S, 1.0 } };
    Actor a2 = mk_actor(both, 2);
    MatchResult r2 = run_ok(&a2, &d, NULL);
    CHECK_NEAR(r2.score, 1.0);
    match_result_free(&r2);
}

/* T12 - demanda sem tags: nao avaliavel (diferente de MISSING) */
static void test_12_empty_demand(void)
{
    ActorTag at[] = { { AI, 1.0 } };
    Actor a = mk_actor(at, N(at));
    Demand d = mk_demand(NULL, 0);
    MatchResult r = run_ok(&a, &d, NULL);
    CHECK(r.status == MATCH_STATUS_NOT_EVALUABLE);
    CHECK_NEAR(r.score, 0.0);
    CHECK(r.details == NULL && r.required_count == 0 && r.desirable_count == 0);
    CHECK(r.actor_id == 42 && r.demand_id == 10);
    match_result_free(&r);
}

/* T13 - ator sem tags: avaliado, tudo MISSING */
static void test_13_actor_without_tags(void)
{
    DemandTag dt[] = { REQ(AI, 1.0), DES(LLM, 1.0) };
    Actor a = mk_actor(NULL, 0);
    Demand d = mk_demand(dt, N(dt));
    MatchResult r = run_ok(&a, &d, NULL);
    CHECK(r.status == MATCH_STATUS_EVALUATED);
    CHECK_NEAR(r.score, 0.0);
    CHECK(r.match_class == MATCH_CLASS_NONE);
    CHECK(match_result_required(&r)[0].match == MATCH_MISSING);
    CHECK(match_result_desirable(&r)[0].match == MATCH_MISSING);
    match_result_free(&r);
}

/* T14 - relacao existe, mas na direcao errada */
static void test_14_wrong_direction(void)
{
    ActorTag at[] = { { ML, 1.0 } };
    DemandTag dt[] = { REQ(LLM, 1.0) };
    Actor a = mk_actor(at, N(at));
    Demand d = mk_demand(dt, N(dt));

    TagRelationship wrong[] = { REL(LLM, ML, RELATION_RELATED, 0.8) }; 
    RelationSet rw = mk_rels(wrong, 1);
    MatchResult r1 = run_ok(&a, &d, &rw);
    CHECK(match_result_required(&r1)[0].match == MATCH_MISSING);
    CHECK_NEAR(r1.score, 0.0);
    match_result_free(&r1);

    TagRelationship right[] = { REL(ML, LLM, RELATION_RELATED, 0.8) };
    RelationSet rr = mk_rels(right, 1);
    MatchResult r2 = run_ok(&a, &d, &rr);
    CHECK(match_result_required(&r2)[0].match == MATCH_RELATED);
    match_result_free(&r2);
}

static void test_15_exact_beats_related(void)
{
    ActorTag at[] = { { LLM, 0.3 }, { ML, 1.0 } };
    DemandTag dt[] = { REQ(LLM, 1.0) };
    TagRelationship rl[] = { REL(ML, LLM, RELATION_RELATED, 1.0) };
    Actor a = mk_actor(at, N(at));
    Demand d = mk_demand(dt, N(dt));
    RelationSet rs = mk_rels(rl, N(rl));
    MatchResult r = run_ok(&a, &d, &rs);
    CHECK(match_result_required(&r)[0].match == MATCH_EXACT);
    CHECK(match_result_required(&r)[0].actor_tag_id == LLM);
    CHECK_NEAR(r.score, 0.3);
    match_result_free(&r);
}

static void test_16_best_relation_no_sum_order_independent(void)
{
    ActorTag at[] = { { ML, 0.9 }, { DL, 1.0 } };
    DemandTag dt[] = { REQ(LLM, 1.0) };
    TagRelationship ab[] = { REL(ML, LLM, RELATION_RELATED, 0.8), REL(DL, LLM, RELATION_RELATED, 0.5) };
    TagRelationship ba[] = { REL(DL, LLM, RELATION_RELATED, 0.5), REL(ML, LLM, RELATION_RELATED, 0.8) };
    Actor a = mk_actor(at, N(at));
    Demand d = mk_demand(dt, N(dt));
    RelationSet r1s = mk_rels(ab, 2), r2s = mk_rels(ba, 2);
    MatchResult r1 = run_ok(&a, &d, &r1s), r2 = run_ok(&a, &d, &r2s);
    CHECK(match_result_required(&r1)[0].actor_tag_id == ML);
    CHECK(match_result_required(&r2)[0].actor_tag_id == ML);
    CHECK_NEAR(r1.score, 0.72);
    CHECK_NEAR(r1.score, r2.score);
    match_result_free(&r1);
    match_result_free(&r2);
}

static void test_17_deterministic_tie_break(void)
{
    ActorTag at[] = { { ML, 1.0 }, { DL, 1.0 } };
    DemandTag dt[] = { REQ(LLM, 1.0) };
    Actor a = mk_actor(at, N(at));
    Demand d = mk_demand(dt, N(dt));

    TagRelationship o1[] = { REL(ML, LLM, RELATION_RELATED, 0.5), REL(DL, LLM, RELATION_RELATED, 0.5) };
    TagRelationship o2[] = { REL(DL, LLM, RELATION_RELATED, 0.5), REL(ML, LLM, RELATION_RELATED, 0.5) };
    RelationSet s1 = mk_rels(o1, 2), s2 = mk_rels(o2, 2);
    MatchResult r1 = run_ok(&a, &d, &s1), r2 = run_ok(&a, &d, &s2);
    CHECK(match_result_required(&r1)[0].actor_tag_id == ML);
    CHECK(match_result_required(&r2)[0].actor_tag_id == ML);
    match_result_free(&r1);
    match_result_free(&r2);

    TagRelationship t1[] = { REL(ML, LLM, RELATION_RELATED, 0.5), REL(ML, LLM, RELATION_SYNONYM, 0.5) };
    TagRelationship t2[] = { REL(ML, LLM, RELATION_SYNONYM, 0.5), REL(ML, LLM, RELATION_RELATED, 0.5) };
    RelationSet u1 = mk_rels(t1, 2), u2 = mk_rels(t2, 2);
    MatchResult r3 = run_ok(&a, &d, &u1), r4 = run_ok(&a, &d, &u2);
    CHECK(match_result_required(&r3)[0].relation_type == RELATION_SYNONYM);
    CHECK(match_result_required(&r4)[0].relation_type == RELATION_SYNONYM);
    match_result_free(&r3);
    match_result_free(&r4);
}

static void test_18_synonym_and_part_of(void)
{
    ActorTag at[] = { { ML, 1.0 } };
    DemandTag dt[] = { REQ(LLM, 1.0) };
    Actor a = mk_actor(at, N(at));
    Demand d = mk_demand(dt, N(dt));

    TagRelationship syn[] = { REL(ML, LLM, RELATION_SYNONYM, 0.95) };
    RelationSet ss = mk_rels(syn, 1);
    MatchResult r1 = run_ok(&a, &d, &ss);
    CHECK(match_result_required(&r1)[0].match == MATCH_RELATED);
    CHECK(match_result_required(&r1)[0].relation_type == RELATION_SYNONYM);
    CHECK_NEAR(r1.score, 0.95);
    match_result_free(&r1);

    TagRelationship syn_rev[] = { REL(LLM, ML, RELATION_SYNONYM, 0.95) };
    RelationSet sr = mk_rels(syn_rev, 1);
    MatchResult r2 = run_ok(&a, &d, &sr);
    CHECK(match_result_required(&r2)[0].match == MATCH_MISSING);
    match_result_free(&r2);

    TagRelationship part[] = { REL(ML, LLM, RELATION_PART_OF, 1.0) };
    RelationSet ps = mk_rels(part, 1);
    MatchResult r3 = run_ok(&a, &d, &ps);
    CHECK(match_result_required(&r3)[0].match == MATCH_MISSING);
    match_result_free(&r3);
}

static void test_19_desirable_cannot_compensate_required(void)
{
    DemandTag dt[] = { REQ(JAVA, 1.0), REQ(SPRING, 1.0), DES(DOCKER, 1.0), DES(K8S, 1.0) };
    Demand d = mk_demand(dt, N(dt));

    ActorTag core[] = { { JAVA, 1.0 }, { SPRING, 1.0 } };
    ActorTag core_d1[] = { { JAVA, 1.0 }, { SPRING, 1.0 }, { DOCKER, 1.0 } };
    ActorTag all[] = { { JAVA, 1.0 }, { SPRING, 1.0 }, { DOCKER, 1.0 }, { K8S, 1.0 } };
    ActorTag no_spring[] = { { JAVA, 1.0 }, { DOCKER, 1.0 }, { K8S, 1.0 } };
    Actor a1 = mk_actor(core, 2), a2 = mk_actor(core_d1, 3), a3 = mk_actor(all, 4),
          a4 = mk_actor(no_spring, 3);
    MatchResult r1 = run_ok(&a1, &d, NULL), r2 = run_ok(&a2, &d, NULL),
                r3 = run_ok(&a3, &d, NULL), r4 = run_ok(&a4, &d, NULL);

    CHECK_NEAR(r1.score, 0.8);
    CHECK_NEAR(r2.score, 0.9);
    CHECK_NEAR(r3.score, 1.0);
    CHECK_NEAR(r4.score, 0.5);
    CHECK(r4.score < r1.score);      
    CHECK(r1.score < r3.score);     
    CHECK(r4.score <= r4.required_score + 1e-12); 
    match_result_free(&r1); match_result_free(&r2);
    match_result_free(&r3); match_result_free(&r4);
}

static void test_20_config_desirable_share(void)
{
    DemandTag dt[] = { REQ(JAVA, 1.0), DES(DOCKER, 1.0) };
    ActorTag at[] = { { JAVA, 1.0 } };
    Actor a = mk_actor(at, 1);
    Demand d = mk_demand(dt, N(dt));

    MatchConfig zero = { 0.0 };
    MatchResult r0 = { 0 };
    CHECK(matcher_run(&a, &d, NULL, &zero, &r0) == MATCHER_OK);
    CHECK_NEAR(r0.score, 1.0);
    match_result_free(&r0);

    MatchConfig half = { 0.5 };
    MatchResult r1 = { 0 };
    CHECK(matcher_run(&a, &d, NULL, &half, &r1) == MATCHER_OK);
    CHECK_NEAR(r1.score, 0.5);
    match_result_free(&r1);

    MatchResult r2 = run_ok(&a, &d, NULL); 
    CHECK_NEAR(r2.score, 0.8);
    match_result_free(&r2);
}

static void test_21_score_bounds(void)
{
    double ws[] = { 0.01, 0.3, 0.5, 1.0 };
    TagRelationship rl[] = { REL(ML, LLM, RELATION_RELATED, 1.0) };
    RelationSet rs = mk_rels(rl, 1);
    for (size_t i = 0; i < N(ws); i++) {
        for (size_t j = 0; j < N(ws); j++) {
            ActorTag at[] = { { AI, ws[i] }, { ML, ws[j] } };
            DemandTag dt[] = { REQ(AI, ws[j]), REQ(PYTHON, 0.2), DES(LLM, ws[i]) };
            Actor a = mk_actor(at, N(at));
            Demand d = mk_demand(dt, N(dt));
            MatchResult r = run_ok(&a, &d, &rs);
            CHECK(r.score >= 0.0 && r.score <= 1.0);
            CHECK(r.required_score >= 0.0 && r.required_score <= 1.0);
            CHECK(r.desirable_score >= 0.0 && r.desirable_score <= 1.0);
            match_result_free(&r);
        }
    }
}

static void test_22_input_validation(void)
{
    DemandTag good_d[] = { REQ(AI, 1.0) };
    Demand d = mk_demand(good_d, 1);
    ActorTag good_a[] = { { AI, 1.0 } };
    Actor a = mk_actor(good_a, 1);

    ActorTag w0[] = { { AI, -0.1 } }, w2[] = { { AI, 1.5 } }, wn[] = { { AI, NAN } };
    Actor a_w0 = mk_actor(w0, 1), a_w2 = mk_actor(w2, 1), a_wn = mk_actor(wn, 1);
    expect_err(&a_w0, &d, NULL, NULL, MATCHER_ERR_INVALID_WEIGHT);
    expect_err(&a_w2, &d, NULL, NULL, MATCHER_ERR_INVALID_WEIGHT);
    expect_err(&a_wn, &d, NULL, NULL, MATCHER_ERR_INVALID_WEIGHT);

    
    ActorTag id0[] = { { 0, 1.0 } }, dup[] = { { AI, 1.0 }, { AI, 0.5 } };
    Actor a_id0 = mk_actor(id0, 1), a_dup = mk_actor(dup, 2);
    expect_err(&a_id0, &d, NULL, NULL, MATCHER_ERR_INVALID_TAG_ID);
    expect_err(&a_dup, &d, NULL, NULL, MATCHER_ERR_DUPLICATE_TAG);

    DemandTag dw0[] = { REQ(AI, 0.0) }, dwneg[] = { REQ(AI, -1.0) }, dwinf[] = { REQ(AI, INFINITY) };
    DemandTag ddup[] = { REQ(AI, 1.0), DES(AI, 1.0) };
    DemandTag dbad[] = { { AI, (TagType)99, 1.0 } };
    DemandTag did[] = { REQ(-5, 1.0) };
    Demand d_w0 = mk_demand(dw0, 1), d_neg = mk_demand(dwneg, 1), d_inf = mk_demand(dwinf, 1),
           d_dup = mk_demand(ddup, 2), d_bad = mk_demand(dbad, 1), d_id = mk_demand(did, 1);
    expect_err(&a, &d_w0, NULL, NULL, MATCHER_ERR_INVALID_WEIGHT);
    expect_err(&a, &d_neg, NULL, NULL, MATCHER_ERR_INVALID_WEIGHT);
    expect_err(&a, &d_inf, NULL, NULL, MATCHER_ERR_INVALID_WEIGHT);
    expect_err(&a, &d_dup, NULL, NULL, MATCHER_ERR_DUPLICATE_TAG);
    expect_err(&a, &d_bad, NULL, NULL, MATCHER_ERR_INVALID_TAG_TYPE);
    expect_err(&a, &d_id, NULL, NULL, MATCHER_ERR_INVALID_TAG_ID);

    Actor a_null = { 1, ACTOR_TYPE_SOLVER, ACTOR_STATUS_ACTIVE, NULL, 3 };
    Demand d_null = { 1, NULL, 2 };
    expect_err(&a_null, &d, NULL, NULL, MATCHER_ERR_NULL_ARG);
    expect_err(&a, &d_null, NULL, NULL, MATCHER_ERR_NULL_ARG);
    RelationSet r_null = { NULL, 4 };
    expect_err(&a, &d, &r_null, NULL, MATCHER_ERR_NULL_ARG);

    DemandTag ld[] = { REQ(LLM, 1.0) };
    Demand dl = mk_demand(ld, 1);
    ActorTag la[] = { { ML, 1.0 } };
    Actor al = mk_actor(la, 1);
    TagRelationship bad_rel[] = { REL(ML, LLM, RELATION_RELATED, 2.0) };
    RelationSet brs = mk_rels(bad_rel, 1);
    expect_err(&al, &dl, &brs, NULL, MATCHER_ERR_INVALID_WEIGHT);

    MatchConfig c1 = { 1.0001 }, c2 = { -0.1 }, c3 = { NAN };
    expect_err(&a, &d, NULL, &c1, MATCHER_ERR_INVALID_CONFIG);
    expect_err(&a, &d, NULL, &c2, MATCHER_ERR_INVALID_CONFIG);
    expect_err(&a, &d, NULL, &c3, MATCHER_ERR_INVALID_CONFIG);

    MatchResult r;
    CHECK(matcher_run(NULL, &d, NULL, NULL, &r) == MATCHER_ERR_NULL_ARG);
    CHECK(matcher_run(&a, NULL, NULL, NULL, &r) == MATCHER_ERR_NULL_ARG);
    CHECK(matcher_run(&a, &d, NULL, NULL, NULL) == MATCHER_ERR_NULL_ARG);
}

static void test_23_free_is_idempotent(void)
{
    ActorTag at[] = { { AI, 1.0 } };
    DemandTag dt[] = { REQ(AI, 1.0) };
    Actor a = mk_actor(at, 1);
    Demand d = mk_demand(dt, 1);
    MatchResult r = run_ok(&a, &d, NULL);
    CHECK(r.details != NULL);
    match_result_free(&r);
    CHECK(r.details == NULL && r.required_count == 0);
    match_result_free(&r);
    match_result_free(NULL);
    CHECK(match_result_required(NULL) == NULL);
}

static void test_24_detail_ordering_and_metadata(void)
{
    DemandTag dt[] = { DES(LLM, 1.0), REQ(AI, 1.0), DES(DOCKER, 1.0), REQ(PYTHON, 1.0) };
    ActorTag at[] = { { AI, 1.0 } };
    Actor a = mk_actor(at, 1);
    Demand d = mk_demand(dt, N(dt));
    MatchResult r = run_ok(&a, &d, NULL);
    CHECK(r.required_count == 2 && r.desirable_count == 2);
    CHECK(r.details[0].demand_tag_id == AI && r.details[1].demand_tag_id == PYTHON);
    CHECK(r.details[2].demand_tag_id == LLM && r.details[3].demand_tag_id == DOCKER);
    CHECK(r.details[0].tag_type == TAG_TYPE_REQUIRED && r.details[2].tag_type == TAG_TYPE_DESIRABLE);
    CHECK(r.actor_id == 42 && r.demand_id == 10);
    CHECK(strcmp(r.algorithm_version, MATCHER_ALGORITHM_VERSION) == 0);
    match_result_free(&r);
}

static void test_25_spec_example_and_report(void)
{
    Tag tags[] = { { AI, "AI" }, { PYTHON, "PYTHON" }, { ML, "MACHINE_LEARNING" }, { LLM, "LLM" } };
    TagCatalog cat = { tags, N(tags) };
    ActorTag at[] = { { AI, 1.0 }, { PYTHON, 1.0 }, { ML, 1.0 } };
    DemandTag dt[] = { REQ(AI, 1.0), REQ(PYTHON, 1.0), DES(LLM, 1.0) };
    TagRelationship rl[] = { REL(ML, LLM, RELATION_RELATED, 0.8) };
    Actor a = mk_actor(at, N(at));
    Demand d = mk_demand(dt, N(dt));
    RelationSet rs = mk_rels(rl, N(rl));
    MatchResult r = run_ok(&a, &d, &rs);

    const MatchDetail *des = match_result_desirable(&r);
    CHECK(strcmp(tag_catalog_code(&cat, des[0].demand_tag_id), "LLM") == 0);
    CHECK(strcmp(tag_catalog_code(&cat, des[0].actor_tag_id), "MACHINE_LEARNING") == 0);
    CHECK(tag_catalog_code(&cat, 999) == NULL);
    CHECK(tag_catalog_code(NULL, 1) == NULL);

    FILE *sink = tmpfile();
    CHECK(sink != NULL);
    if (sink != NULL) {
        match_result_print(sink, &r, &cat);
        long len = ftell(sink);
        CHECK(len > 0);
        fclose(sink);
    }
    match_result_free(&r);
}

static double score_of(const ActorTag *at, size_t na, const DemandTag *dt, size_t nd)
{
    Actor a = mk_actor(at, na);
    Demand d = mk_demand(dt, nd);
    MatchResult r = run_ok(&a, &d, NULL);
    double s = r.score;
    match_result_free(&r);
    return s;
}

static double score_cfg(const ActorTag *at, size_t na, const DemandTag *dt, size_t nd, double share)
{
    Actor a = mk_actor(at, na);
    Demand d = mk_demand(dt, nd);
    MatchConfig cfg = { share };
    MatchResult r;
    MatcherError e = matcher_run(&a, &d, NULL, &cfg, &r);
    CHECK(e == MATCHER_OK);
    double s = r.score;
    match_result_free(&r);
    return s;
}


static void test_26_share_zero_score_is_R(void)
{
    DemandTag dt[] = { REQ(JAVA, 1.0), REQ(SPRING, 1.0), DES(DOCKER, 1.0) };
    ActorTag at[] = { { JAVA, 1.0 }, { DOCKER, 1.0 } };
    CHECK_NEAR(score_cfg(at, N(at), dt, N(dt), 0.0), 0.5);
    ActorTag none[] = { { JAVA, 1.0 }, { SPRING, 1.0 } }; 
    CHECK_NEAR(score_cfg(none, N(none), dt, N(dt), 0.0), 1.0);
}

static void test_27_share_one_score_is_R_times_D(void)
{
    CHECK(matcher_validate_config(&(MatchConfig){ 1.0 }) == MATCHER_OK);
    DemandTag dt[] = { REQ(JAVA, 1.0), REQ(SPRING, 1.0), DES(DOCKER, 1.0), DES(K8S, 1.0) };

    ActorTag a1[] = { { JAVA, 1.0 }, { SPRING, 1.0 }, { DOCKER, 1.0 } }; 
    CHECK_NEAR(score_cfg(a1, N(a1), dt, N(dt), 1.0), 0.5);
    ActorTag a2[] = { { JAVA, 1.0 }, { DOCKER, 1.0 } };                  
    CHECK_NEAR(score_cfg(a2, N(a2), dt, N(dt), 1.0), 0.25);
    ActorTag a3[] = { { JAVA, 1.0 }, { SPRING, 1.0 } };                 
    CHECK_NEAR(score_cfg(a3, N(a3), dt, N(dt), 1.0), 0.0);

   
    DemandTag only_r[] = { REQ(JAVA, 1.0) };
    ActorTag j[] = { { JAVA, 1.0 } };
    CHECK_NEAR(score_cfg(j, 1, only_r, 1, 1.0), 1.0);
    DemandTag only_d[] = { DES(JAVA, 1.0) };
    CHECK_NEAR(score_cfg(j, 1, only_d, 1, 1.0), 1.0);

    CHECK(matcher_validate_config(&(MatchConfig){ 1.0000001 }) == MATCHER_ERR_INVALID_CONFIG);
    CHECK(matcher_validate_config(&(MatchConfig){ -1e-9 }) == MATCHER_ERR_INVALID_CONFIG);
    CHECK(matcher_validate_config(&(MatchConfig){ INFINITY }) == MATCHER_ERR_INVALID_CONFIG);
    CHECK(matcher_validate_config(NULL) == MATCHER_ERR_NULL_ARG);
    CHECK(matcher_validate_config(&(MatchConfig){ 0.0 }) == MATCHER_OK);
}

static void test_28_required_perfect_desirable_absent(void)
{
    DemandTag dt[] = { REQ(JAVA, 1.0), DES(DOCKER, 1.0) };
    ActorTag at[] = { { JAVA, 1.0 } };
    Actor a = mk_actor(at, 1);
    Demand d = mk_demand(dt, 2);
    MatchResult r = run_ok(&a, &d, NULL);
    CHECK_NEAR(r.required_score, 1.0);
    CHECK_NEAR(r.desirable_score, 0.0);
    CHECK_NEAR(r.score, 0.80);
    match_result_free(&r);
}

static void test_29_required_absent_desirable_perfect(void)
{
    DemandTag dt[] = { REQ(JAVA, 1.0), DES(DOCKER, 1.0) };
    ActorTag at[] = { { DOCKER, 1.0 } };
    double shares[] = { 0.0, 0.2, 0.5, 1.0 };
    for (size_t i = 0; i < N(shares); i++) {
        CHECK_NEAR(score_cfg(at, 1, dt, 2, shares[i]), 0.0);
    }
}

static void test_30_actor_weight_zero(void)
{
    DemandTag dt[] = { REQ(JAVA, 1.0) };
    ActorTag at[] = { { JAVA, 0.0 } };
    Actor a = mk_actor(at, 1);
    Demand d = mk_demand(dt, 1);
    MatchResult r = run_ok(&a, &d, NULL);
    const MatchDetail *x = match_result_required(&r);
    CHECK(x[0].match == MATCH_MISSING);
    CHECK_NEAR(x[0].coverage, 0.0);
    CHECK_NEAR(r.score, 0.0);
    CHECK(r.required_missing_count == 1);
    CHECK(r.match_class == MATCH_CLASS_NONE);
    match_result_free(&r);

    ActorTag both[] = { { JAVA, 0.0 }, { ML, 0.9 } };
    TagRelationship rl[] = { REL(ML, JAVA, RELATION_RELATED, 0.5) };
    Actor a2 = mk_actor(both, 2);
    RelationSet rs = mk_rels(rl, 1);
    MatchResult r2 = run_ok(&a2, &d, &rs);
    CHECK(match_result_required(&r2)[0].match == MATCH_RELATED);
    CHECK_NEAR(r2.score, 0.45);
    match_result_free(&r2);

    ActorTag neg[] = { { JAVA, -0.01 } };
    Actor an = mk_actor(neg, 1);
    expect_err(&an, &d, NULL, NULL, MATCHER_ERR_INVALID_WEIGHT);
}

static void test_31_relation_weight_zero(void)
{
    ActorTag at[] = { { ML, 1.0 } };
    DemandTag dt[] = { REQ(LLM, 1.0) };
    Actor a = mk_actor(at, 1);
    Demand d = mk_demand(dt, 1);

    TagRelationship zero[] = { REL(ML, LLM, RELATION_RELATED, 0.0) };
    RelationSet rz = mk_rels(zero, 1);
    MatchResult r = run_ok(&a, &d, &rz);
    CHECK(match_result_required(&r)[0].match == MATCH_MISSING);
    CHECK_NEAR(match_result_required(&r)[0].coverage, 0.0);
    CHECK_NEAR(r.score, 0.0);
    CHECK(r.required_missing_count == 1);
    match_result_free(&r);

    ActorTag weak[] = { { ML, 0.0 } };
    TagRelationship strong[] = { REL(ML, LLM, RELATION_RELATED, 0.9) };
    Actor aw = mk_actor(weak, 1);
    RelationSet rstr = mk_rels(strong, 1);
    MatchResult r2 = run_ok(&aw, &d, &rstr);
    CHECK(match_result_required(&r2)[0].match == MATCH_MISSING);
    match_result_free(&r2);

    ActorTag two[] = { { ML, 1.0 }, { DL, 1.0 } };
    TagRelationship mix[] = { REL(ML, LLM, RELATION_RELATED, 0.0), REL(DL, LLM, RELATION_RELATED, 0.3) };
    Actor a2 = mk_actor(two, 2);
    RelationSet rm = mk_rels(mix, 2);
    MatchResult r3 = run_ok(&a2, &d, &rm);
    CHECK(match_result_required(&r3)[0].actor_tag_id == DL);
    CHECK_NEAR(r3.score, 0.3);
    match_result_free(&r3);
}

static void test_32_demand_weight_dominance(void)
{
    DemandTag dt[] = { REQ(JAVA, 10.0), REQ(SPRING, 1.0) };
    ActorTag only_java[] = { { JAVA, 1.0 } };
    ActorTag only_spring[] = { { SPRING, 1.0 } };
    ActorTag both[] = { { JAVA, 1.0 }, { SPRING, 1.0 } };
    CHECK_NEAR(score_of(only_java, 1, dt, 2), 10.0 / 11.0);
    CHECK_NEAR(score_of(only_spring, 1, dt, 2), 1.0 / 11.0);
    CHECK_NEAR(score_of(both, 2, dt, 2), 1.0);
    CHECK(score_of(only_java, 1, dt, 2) > 9.0 * score_of(only_spring, 1, dt, 2));
}

static void test_33_demand_weight_zero_rejected(void)
{
    ActorTag at[] = { { JAVA, 1.0 } };
    Actor a = mk_actor(at, 1);

    DemandTag z[] = { REQ(JAVA, 0.0) };
    DemandTag mixed_zero[] = { REQ(JAVA, 1.0), DES(DOCKER, 0.0) };
    DemandTag neg[] = { REQ(JAVA, -0.5) };
    DemandTag nan_w[] = { REQ(JAVA, NAN) };
    Demand d1 = mk_demand(z, 1), d2 = mk_demand(mixed_zero, 2), d3 = mk_demand(neg, 1),
           d4 = mk_demand(nan_w, 1);
    expect_err(&a, &d1, NULL, NULL, MATCHER_ERR_INVALID_WEIGHT);
    expect_err(&a, &d2, NULL, NULL, MATCHER_ERR_INVALID_WEIGHT);
    expect_err(&a, &d3, NULL, NULL, MATCHER_ERR_INVALID_WEIGHT);
    expect_err(&a, &d4, NULL, NULL, MATCHER_ERR_INVALID_WEIGHT);
    CHECK(matcher_validate_demand(&d1) == MATCHER_ERR_INVALID_WEIGHT);

    DemandTag huge[] = { REQ(JAVA, 1e308), REQ(SPRING, 1e308) };
    Demand dh = mk_demand(huge, 2);
    expect_err(&a, &dh, NULL, NULL, MATCHER_ERR_INVALID_WEIGHT);

    DemandTag one_huge[] = { REQ(JAVA, 1e308) };
    CHECK_NEAR(score_of(at, 1, one_huge, 1), 1.0);
}

static void test_34_multiple_relations_all_permutations(void)
{
    ActorTag at[] = { { ML, 0.9 }, { DL, 1.0 }, { AI, 0.6 } };
    DemandTag dt[] = { REQ(LLM, 1.0) };
    TagRelationship base[3] = { REL(ML, LLM, RELATION_RELATED, 0.8),  
                                REL(DL, LLM, RELATION_RELATED, 0.5),   
                                REL(AI, LLM, RELATION_SYNONYM, 1.0) }; 
    static const int perms[6][3] = { {0,1,2}, {0,2,1}, {1,0,2}, {1,2,0}, {2,0,1}, {2,1,0} };
    Actor a = mk_actor(at, N(at));
    Demand d = mk_demand(dt, 1);

    for (int p = 0; p < 6; p++) {
        TagRelationship rl[3];
        for (int i = 0; i < 3; i++) rl[i] = base[perms[p][i]];
        RelationSet rs = mk_rels(rl, 3);
        MatchResult r = run_ok(&a, &d, &rs);
        CHECK(match_result_required(&r)[0].match == MATCH_RELATED);
        CHECK(match_result_required(&r)[0].actor_tag_id == ML);
        CHECK_NEAR(r.score, 0.72);         
        CHECK(r.score <= 0.72 + 1e-12);
        match_result_free(&r);
    }

  
    ActorTag with_exact[] = { { ML, 0.9 }, { DL, 1.0 }, { AI, 0.6 }, { LLM, 0.3 } };
    Actor ae = mk_actor(with_exact, 4);
    for (int p = 0; p < 6; p++) {
        TagRelationship rl[3];
        for (int i = 0; i < 3; i++) rl[i] = base[perms[p][i]];
        RelationSet rs = mk_rels(rl, 3);
        MatchResult r = run_ok(&ae, &d, &rs);
        CHECK(match_result_required(&r)[0].match == MATCH_EXACT);
        CHECK_NEAR(r.score, 0.3);
        match_result_free(&r);
    }
}


static void test_35_extra_actor_tags_exactly_equal(void)
{
    DemandTag dt[] = { REQ(AI, 0.7), REQ(LLM, 0.3), DES(DOCKER, 0.5) };
    ActorTag base[] = { { AI, 0.9 }, { ML, 0.6 } };
    ActorTag extra[] = { { AI, 0.9 }, { ML, 0.6 }, { JAVA, 1.0 }, { SPRING, 1.0 },
                         { K8S, 1.0 }, { PYTHON, 1.0 }, { DL, 1.0 } };
    TagRelationship rl[] = { REL(ML, LLM, RELATION_RELATED, 0.8),
                             REL(JAVA, SPRING, RELATION_RELATED, 1.0),   
                             REL(K8S, DOCKER, RELATION_RELATED, 0.0) };
    Demand d = mk_demand(dt, N(dt));
    RelationSet rs = mk_rels(rl, N(rl));
    Actor a1 = mk_actor(base, N(base)), a2 = mk_actor(extra, N(extra));
    MatchResult r1 = run_ok(&a1, &d, &rs), r2 = run_ok(&a2, &d, &rs);
    CHECK(r1.score == r2.score);
    CHECK(r1.required_score == r2.required_score);
    CHECK(r1.desirable_score == r2.desirable_score);
    CHECK(r1.match_class == r2.match_class);
    CHECK(r1.required_missing_count == r2.required_missing_count);
    for (size_t i = 0; i < r1.required_count + r1.desirable_count; i++) {
        CHECK(r1.details[i].match == r2.details[i].match);
        CHECK(r1.details[i].coverage == r2.details[i].coverage);
        CHECK(r1.details[i].actor_tag_id == r2.details[i].actor_tag_id);
    }
    match_result_free(&r1);
    match_result_free(&r2);
}


static void test_36_extra_demand_tags_effect(void)
{
    ActorTag at[] = { { JAVA, 0.5 }, { SPRING, 1.0 }, { PYTHON, 0.5 } };
    DemandTag base[] = { REQ(JAVA, 1.0) };
    CHECK_NEAR(score_of(at, N(at), base, 1), 0.5);

    
    DemandTag add_missing[] = { REQ(JAVA, 1.0), REQ(DOCKER, 1.0) };
    CHECK_NEAR(score_of(at, N(at), add_missing, 2), 0.25);
    
    DemandTag add_better[] = { REQ(JAVA, 1.0), REQ(SPRING, 1.0) };
    CHECK_NEAR(score_of(at, N(at), add_better, 2), 0.75);
    
    DemandTag add_equal[] = { REQ(JAVA, 1.0), REQ(PYTHON, 1.0) };
    CHECK_NEAR(score_of(at, N(at), add_equal, 2), 0.5);

    
    double ws[] = { 0.01, 0.5, 1.0, 7.0 };
    for (size_t i = 0; i < N(ws); i++) {
        DemandTag more[] = { REQ(JAVA, 1.0), REQ(DOCKER, ws[i]) };
        CHECK(score_of(at, N(at), more, 2) <= score_of(at, N(at), base, 1) + 1e-12);
        DemandTag more_d[] = { REQ(JAVA, 1.0), DES(DOCKER, ws[i]) };
        CHECK(score_of(at, N(at), more_d, 2) <= score_of(at, N(at), base, 1) + 1e-12);
    }

    ActorTag full[] = { { JAVA, 1.0 }, { DOCKER, 1.0 } };
    DemandTag r_only[] = { REQ(JAVA, 1.0) };
    DemandTag add_des_missing[] = { REQ(JAVA, 1.0), DES(K8S, 1.0) };
    DemandTag add_des_present[] = { REQ(JAVA, 1.0), DES(DOCKER, 1.0) };
    CHECK_NEAR(score_of(full, 2, r_only, 1), 1.0);
    CHECK_NEAR(score_of(full, 2, add_des_missing, 2), 0.8);
    CHECK_NEAR(score_of(full, 2, add_des_present, 2), 1.0);

    DemandTag more_full[] = { REQ(JAVA, 1.0), REQ(DOCKER, 3.0) };
    CHECK_NEAR(score_of(full, 2, more_full, 2), 1.0);
}



static MatchClass class_of(const ActorTag *at, size_t na, const DemandTag *dt, size_t nd)
{
    TagRelationship rl[] = { REL(ML, LLM, RELATION_RELATED, 0.8), REL(DL, DOCKER, RELATION_SYNONYM, 0.8) };
    Actor a = mk_actor(at, na);
    Demand d = mk_demand(dt, nd);
    RelationSet rs = mk_rels(rl, N(rl));
    MatchResult r = run_ok(&a, &d, &rs);
    MatchClass c = r.match_class;
    match_result_free(&r);
    return c;
}

static void test_37_match_class_truth_table(void)
{
    ActorTag a_ai_py[] = { { AI, 1.0 }, { PYTHON, 1.0 } };
    ActorTag a_ai_ml[] = { { AI, 1.0 }, { ML, 1.0 } };
    ActorTag a_ml_dl[] = { { ML, 1.0 }, { DL, 1.0 } };
    ActorTag a_ai[]    = { { AI, 1.0 } };
    ActorTag a_ml[]    = { { ML, 1.0 } };
    ActorTag a_java[]  = { { JAVA, 1.0 } };
    ActorTag a_weak[]  = { { AI, 0.1 } };

    DemandTag d_ai_py[]     = { REQ(AI, 1.0), REQ(PYTHON, 1.0) };
    DemandTag d_ai_llm[]    = { REQ(AI, 1.0), REQ(LLM, 1.0) };
    DemandTag d_llm_dock[]  = { REQ(LLM, 1.0), REQ(DOCKER, 1.0) };
    DemandTag d_llm_py[]    = { REQ(LLM, 1.0), REQ(PYTHON, 1.0) };
    DemandTag d_ai_llm_py[] = { REQ(AI, 1.0), REQ(LLM, 1.0), REQ(PYTHON, 1.0) };
    DemandTag d_ai[]        = { REQ(AI, 1.0) };

    CHECK(class_of(a_ai_py, 2, d_ai_py, 2) == MATCH_CLASS_EXACT);     
    CHECK(class_of(a_ai_ml, 2, d_ai_llm, 2) == MATCH_CLASS_RELATED);  
    CHECK(class_of(a_ml_dl, 2, d_llm_dock, 2) == MATCH_CLASS_RELATED);
    CHECK(class_of(a_ai, 1, d_ai_py, 2) == MATCH_CLASS_PARTIAL);   
    CHECK(class_of(a_ml, 1, d_llm_py, 2) == MATCH_CLASS_PARTIAL);    
    CHECK(class_of(a_ai_ml, 2, d_ai_llm_py, 3) == MATCH_CLASS_PARTIAL);
    CHECK(class_of(a_java, 1, d_ai_py, 2) == MATCH_CLASS_NONE);      
    CHECK(class_of(a_weak, 1, d_ai, 1) == MATCH_CLASS_EXACT);       


    DemandTag r_exact_d_missing[] = { REQ(AI, 1.0), DES(PYTHON, 1.0) };
    DemandTag r_exact_d_related[] = { REQ(AI, 1.0), DES(LLM, 1.0) };
    CHECK(class_of(a_ai, 1, r_exact_d_missing, 2) == MATCH_CLASS_EXACT);
    CHECK(class_of(a_ai_ml, 2, r_exact_d_related, 2) == MATCH_CLASS_EXACT);

   
    DemandTag only_d_related[] = { DES(LLM, 1.0) };
    DemandTag only_d_partial[] = { DES(AI, 1.0), DES(PYTHON, 1.0) };
    CHECK(class_of(a_ml, 1, only_d_related, 1) == MATCH_CLASS_RELATED);
    CHECK(class_of(a_ai, 1, only_d_partial, 2) == MATCH_CLASS_PARTIAL);
}


static void test_38_missing_iff_zero_coverage(void)
{
    double ws[] = { 0.0, 1e-3, 0.5, 1.0 };
    DemandTag dt[] = { REQ(AI, 1.0), REQ(LLM, 2.0), DES(DOCKER, 1.0), DES(PYTHON, 1.0) };
    Demand d = mk_demand(dt, N(dt));
    for (size_t i = 0; i < N(ws); i++) {
        for (size_t j = 0; j < N(ws); j++) {
            for (size_t k = 0; k < N(ws); k++) {
                ActorTag at[] = { { AI, ws[i] }, { ML, ws[j] }, { DL, 1.0 } };
                TagRelationship rl[] = { REL(ML, LLM, RELATION_RELATED, ws[k]),
                                         REL(DL, DOCKER, RELATION_SYNONYM, ws[k]) };
                Actor a = mk_actor(at, N(at));
                RelationSet rs = mk_rels(rl, N(rl));
                MatchResult r = run_ok(&a, &d, &rs);
                size_t missing_req = 0;
                for (size_t x = 0; x < r.required_count + r.desirable_count; x++) {
                    const MatchDetail *m = &r.details[x];
                    CHECK((m->match == MATCH_MISSING) == (m->coverage == 0.0));
                    CHECK(m->coverage >= 0.0 && m->coverage <= 1.0);
                    if (x < r.required_count && m->match == MATCH_MISSING) missing_req++;
                }
                CHECK(missing_req == r.required_missing_count);
                CHECK(r.score >= 0.0 && r.score <= r.required_score + 1e-12);
                match_result_free(&r);
            }
        }
    }
}

static ActorTag    FX_T1[] = { { AI, 1.0 }, { PYTHON, 1.0 }, { LLM, 1.0 } };
static ActorTag    FX_T2[] = { { AI, 1.0 }, { PYTHON, 1.0 } };
static ActorTag    FX_T3[] = { { AI, 1.0 }, { PYTHON, 1.0 }, { ML, 1.0 } };
static ActorTag    FX_T4[] = { { AI, 1.0 } };
static ActorTag    FX_T5[] = { { JAVA, 1.0 } };
static DemandTag   FX_D[]  = { REQ(AI, 1.0), REQ(PYTHON, 1.0), DES(LLM, 1.0) };
static TagRelationship FX_R[] = { REL(ML, LLM, RELATION_RELATED, 0.8) };

#define FX_N 6
static const int64_t FX_ORDER[FX_N] = { 1, 3, 2, 4, 5, 6 }; 

static void fx_actors(Actor out[FX_N])
{
    const Actor a[FX_N] = {
        { 1, ACTOR_TYPE_SOLVER,       ACTOR_STATUS_ACTIVE, FX_T1, N(FX_T1) },
        { 2, ACTOR_TYPE_STARTUP,      ACTOR_STATUS_ACTIVE, FX_T2, N(FX_T2) },
        { 3, ACTOR_TYPE_SOLVER,       ACTOR_STATUS_ACTIVE, FX_T3, N(FX_T3) },
        { 4, ACTOR_TYPE_SOLVER,       ACTOR_STATUS_ACTIVE, FX_T4, N(FX_T4) },
        { 5, ACTOR_TYPE_SOLVER,       ACTOR_STATUS_ACTIVE, FX_T5, N(FX_T5) },
        { 6, ACTOR_TYPE_ORGANIZATION, ACTOR_STATUS_ACTIVE, NULL, 0 }
    };
    memcpy(out, a, sizeof a);
}

static BatchResult fx_batch(const Actor *actors, size_t n, const BatchOptions *opt)
{
    Demand d = mk_demand(FX_D, N(FX_D));
    RelationSet rs = mk_rels(FX_R, N(FX_R));
    BatchResult b;
    MatcherError e = batch_match(actors, n, &d, &rs, NULL, opt, &b, NULL);
    CHECK(e == MATCHER_OK);
    return b;
}

static void expect_ids(const BatchResult *b, const int64_t *ids, size_t n)
{
    CHECK(b->count == n);
    if (b->count != n) return;
    for (size_t i = 0; i < n; i++) {
        CHECK(b->results[i].actor_id == ids[i]);
    }
}

static uint32_t g_rng = 12345u;
static uint32_t rnd(void)
{
    g_rng = g_rng * 1664525u + 1013904223u;
    return g_rng >> 8;
}

static void shuffle_actors(Actor *a, size_t n)
{
    for (size_t i = n; i > 1; i--) {
        size_t j = rnd() % i;
        Actor t = a[i - 1];
        a[i - 1] = a[j];
        a[j] = t;
    }
}


static void test_40_batch_zero_actors(void)
{
    BatchResult b = fx_batch(NULL, 0, NULL);
    CHECK(b.status == MATCH_STATUS_EVALUATED);
    CHECK(b.count == 0 && b.results == NULL);
    CHECK(b.evaluated_count == 0 && b.passed_count == 0);
    batch_result_free(&b);
}

static void test_41_batch_single_actor(void)
{
    Actor a[FX_N];
    fx_actors(a);
    BatchResult b = fx_batch(&a[2], 1, NULL);
    CHECK(b.count == 1 && b.evaluated_count == 1 && b.passed_count == 1);
    CHECK(b.results[0].actor_id == 3);
    CHECK_NEAR(b.results[0].score, 0.96);
    CHECK(b.results[0].details != NULL);
    CHECK(b.results[0].required_count == 2 && b.results[0].desirable_count == 1);
    CHECK(b.results[0].demand_id == 10);
    batch_result_free(&b);
}

static void test_42_batch_several_sorted_matches_individual(void)
{
    Actor a[FX_N];
    fx_actors(a);
    BatchResult b = fx_batch(a, FX_N, NULL);
    CHECK(b.status == MATCH_STATUS_EVALUATED);
    CHECK(b.evaluated_count == FX_N && b.passed_count == FX_N);
    expect_ids(&b, FX_ORDER, FX_N);

    Demand d = mk_demand(FX_D, N(FX_D));
    RelationSet rs = mk_rels(FX_R, N(FX_R));
    for (size_t i = 0; i < b.count; i++) {
        const MatchResult *r = &b.results[i];
        if (i > 0) CHECK(r->score <= b.results[i - 1].score + 1e-12);

        for (size_t k = 0; k < FX_N; k++) {
            if (a[k].id != r->actor_id) continue;
            MatchResult ref;
            CHECK(matcher_run(&a[k], &d, &rs, NULL, &ref) == MATCHER_OK);
            CHECK(ref.score == r->score);
            CHECK(ref.required_missing_count == r->required_missing_count);
            CHECK(ref.match_class == r->match_class);
            CHECK(ref.required_count == r->required_count && ref.desirable_count == r->desirable_count);
            for (size_t x = 0; x < ref.required_count + ref.desirable_count; x++) {
                CHECK(ref.details[x].match == r->details[x].match);
                CHECK(ref.details[x].coverage == r->details[x].coverage);
            }
            match_result_free(&ref);
        }
    }
    batch_result_free(&b);
}

static void test_43_batch_order_independent_of_input(void)
{
    Actor base[FX_N];
    fx_actors(base);
    for (int round = 0; round < 40; round++) {
        Actor a[FX_N];
        memcpy(a, base, sizeof a);
        shuffle_actors(a, FX_N);
        BatchResult b = fx_batch(a, FX_N, NULL);
        expect_ids(&b, FX_ORDER, FX_N);
        batch_result_free(&b);
    }
}

static void test_44_batch_deterministic_ties(void)
{
    DemandTag dt[] = { REQ(AI, 1.0), REQ(PYTHON, 1.0) };
    Demand d = mk_demand(dt, 2);
    ActorTag tp[] = { { AI, 1.0 } };                 
    ActorTag tq[] = { { AI, 0.5 }, { PYTHON, 0.5 } };
    ActorTag ts[] = { { PYTHON, 1.0 } };         
    Actor base[3] = { { 9, ACTOR_TYPE_SOLVER, ACTOR_STATUS_ACTIVE, tp, 1 },
                      { 7, ACTOR_TYPE_SOLVER, ACTOR_STATUS_ACTIVE, tq, 2 },
                      { 3, ACTOR_TYPE_SOLVER, ACTOR_STATUS_ACTIVE, ts, 1 } };
    const int64_t expect[3] = { 7, 3, 9 }; 

    for (int round = 0; round < 30; round++) {
        Actor a[3];
        memcpy(a, base, sizeof a);
        shuffle_actors(a, 3);
        BatchResult b;
        CHECK(batch_match(a, 3, &d, NULL, NULL, NULL, &b, NULL) == MATCHER_OK);
        expect_ids(&b, expect, 3);
        if (b.count == 3) {
            CHECK_NEAR(b.results[0].score, 0.5);
            CHECK_NEAR(b.results[2].score, 0.5);
            CHECK(b.results[0].required_missing_count == 0);
        }
        batch_result_free(&b);
    }
}

static void test_45_batch_tie_with_float_noise(void)
{
    DemandTag dt[] = { REQ(AI, 0.1), REQ(PYTHON, 0.2) };
    Demand d = mk_demand(dt, 2);
    ActorTag tx[] = { { AI, 0.3 }, { PYTHON, 0.3 } };   
    ActorTag ty[] = { { AI, 0.6 }, { PYTHON, 0.15 } };
    Actor a[2] = { { 2, ACTOR_TYPE_SOLVER, ACTOR_STATUS_ACTIVE, tx, 2 },
                   { 1, ACTOR_TYPE_SOLVER, ACTOR_STATUS_ACTIVE, ty, 2 } };
    BatchResult b;
    CHECK(batch_match(a, 2, &d, NULL, NULL, NULL, &b, NULL) == MATCHER_OK);
    const int64_t expect[2] = { 1, 2 };
    expect_ids(&b, expect, 2);
    batch_result_free(&b);
    Actor rev[2] = { a[1], a[0] };
    CHECK(batch_match(rev, 2, &d, NULL, NULL, NULL, &b, NULL) == MATCHER_OK);
    expect_ids(&b, expect, 2);
    batch_result_free(&b);
}

static void test_46_batch_threshold(void)
{
    Actor a[FX_N];
    fx_actors(a);
    BatchOptions o = batch_default_options();

    o.threshold = 0.8;
    BatchResult b = fx_batch(a, FX_N, &o);
    const int64_t e1[] = { 1, 3, 2 };
    expect_ids(&b, e1, 3);
    CHECK(b.evaluated_count == FX_N && b.passed_count == 3);
    CHECK_NEAR(b.results[2].score, 0.8);
    batch_result_free(&b);

    o.threshold = 0.81;
    b = fx_batch(a, FX_N, &o);
    const int64_t e2[] = { 1, 3 };
    expect_ids(&b, e2, 2);
    batch_result_free(&b);

    o.threshold = 1.0;
    b = fx_batch(a, FX_N, &o);
    const int64_t e3[] = { 1 };
    expect_ids(&b, e3, 1);
    batch_result_free(&b);

    o.threshold = 0.0;
    b = fx_batch(a, FX_N, &o);
    expect_ids(&b, FX_ORDER, FX_N);
    batch_result_free(&b);

    DemandTag hard[] = { REQ(K8S, 1.0) };
    Demand d = mk_demand(hard, 1);
    o.threshold = 0.5;
    CHECK(batch_match(a, FX_N, &d, NULL, NULL, &o, &b, NULL) == MATCHER_OK);
    CHECK(b.count == 0 && b.results == NULL && b.evaluated_count == FX_N && b.passed_count == 0);
    CHECK(b.status == MATCH_STATUS_EVALUATED);
    batch_result_free(&b);
}

static void test_47_batch_threshold_float_boundary(void)
{
    DemandTag dt[] = { REQ(AI, 0.1), REQ(PYTHON, 0.2) };
    Demand d = mk_demand(dt, 2);
    ActorTag at[] = { { AI, 0.3 }, { PYTHON, 0.3 } };
    Actor a = { 1, ACTOR_TYPE_SOLVER, ACTOR_STATUS_ACTIVE, at, 2 };
    BatchOptions o = { 0.3, BATCH_TOP_K_UNLIMITED };
    BatchResult b;
    CHECK(batch_match(&a, 1, &d, NULL, NULL, &o, &b, NULL) == MATCHER_OK);
    CHECK(b.count == 1);                      
    if (b.count == 1) {
        CHECK(b.results[0].score < 0.3);     
        CHECK(fabs(b.results[0].score - 0.3) < 1e-12);
    }
    batch_result_free(&b);

    o.threshold = 0.3000001;                  
    CHECK(batch_match(&a, 1, &d, NULL, NULL, &o, &b, NULL) == MATCHER_OK);
    CHECK(b.count == 0);
    batch_result_free(&b);
}

/* 7) top_k */
static void test_48_batch_top_k(void)
{
    Actor a[FX_N];
    fx_actors(a);
    BatchOptions o = batch_default_options();

    for (size_t k = 1; k <= FX_N; k++) {
        o.top_k = k;
        BatchResult b = fx_batch(a, FX_N, &o);
        expect_ids(&b, FX_ORDER, k);
        CHECK(b.evaluated_count == FX_N && b.passed_count == FX_N); 
        batch_result_free(&b);
    }
    size_t big[] = { FX_N + 1, 1000, BATCH_TOP_K_UNLIMITED };
    for (size_t i = 0; i < N(big); i++) {
        o.top_k = big[i];
        BatchResult b = fx_batch(a, FX_N, &o);
        expect_ids(&b, FX_ORDER, FX_N);
        batch_result_free(&b);
    }
    CHECK(BATCH_TOP_K_UNLIMITED == 0);
}

static void test_49_batch_threshold_and_top_k(void)
{
    Actor a[FX_N];
    fx_actors(a);
    BatchOptions o = { 0.5, 2 };
    BatchResult b = fx_batch(a, FX_N, &o);
    const int64_t e[] = { 1, 3 };
    expect_ids(&b, e, 2);
    CHECK(b.passed_count == 3); 
    batch_result_free(&b);

    o.top_k = 5;
    b = fx_batch(a, FX_N, &o);
    const int64_t e2[] = { 1, 3, 2 };
    expect_ids(&b, e2, 3);
    batch_result_free(&b);

    o.threshold = 0.9; o.top_k = 1;
    b = fx_batch(a, FX_N, &o);
    expect_ids(&b, e, 1);
    batch_result_free(&b);
}

static void test_50_batch_required_missing_preserved(void)
{
    Actor a[FX_N];
    fx_actors(a);
    BatchResult b = fx_batch(a, FX_N, NULL);
    size_t with_missing = 0;
    for (size_t i = 0; i < b.count; i++) {
        const MatchResult *r = &b.results[i];
        if (r->actor_id == 4) CHECK(r->required_missing_count == 1);
        if (r->actor_id == 5 || r->actor_id == 6) CHECK(r->required_missing_count == 2);
        if (r->actor_id == 1 || r->actor_id == 2 || r->actor_id == 3) CHECK(r->required_missing_count == 0);
        if (r->required_missing_count > 0) with_missing++;
    }
    CHECK(with_missing == 3); 
    batch_result_free(&b);

    
    b = fx_batch(a, FX_N, NULL);
    size_t kept = 0;
    for (size_t i = 0; i < b.count; i++) if (b.results[i].required_missing_count == 0) kept++;
    CHECK(kept == 3);
    batch_result_free(&b);
}

static void test_51_batch_score_zero_and_one(void)
{
    Actor a[FX_N];
    fx_actors(a);
    BatchResult b = fx_batch(a, FX_N, NULL);
    CHECK(b.results[0].actor_id == 1);
    CHECK_NEAR(b.results[0].score, 1.0);
    CHECK(b.results[0].required_missing_count == 0 && b.results[0].match_class == MATCH_CLASS_EXACT);
    CHECK(b.results[FX_N - 1].score == 0.0 && b.results[FX_N - 2].score == 0.0);
    CHECK(b.results[FX_N - 2].match_class == MATCH_CLASS_NONE);
    batch_result_free(&b);

    BatchOptions o = batch_default_options();
    o.threshold = 1e-6;
    b = fx_batch(a, FX_N, &o);
    CHECK(b.count == 4);
    for (size_t i = 0; i < b.count; i++) CHECK(b.results[i].score > 0.0);
    batch_result_free(&b);
}

static void test_52_batch_extra_actor_tags(void)
{
    static ActorTag e1[] = { { AI, 1.0 }, { PYTHON, 1.0 }, { LLM, 1.0 }, { JAVA, 1.0 }, { SPRING, 1.0 }, { K8S, 1.0 } };
    static ActorTag e4[] = { { AI, 1.0 }, { DOCKER, 1.0 }, { DL, 1.0 }, { SPRING, 1.0 } };
    Actor plain[FX_N], extra[FX_N];
    fx_actors(plain);
    fx_actors(extra);
    extra[0].tags = e1; extra[0].tag_count = N(e1);
    extra[3].tags = e4; extra[3].tag_count = N(e4);

    BatchResult b1 = fx_batch(plain, FX_N, NULL), b2 = fx_batch(extra, FX_N, NULL);
    CHECK(b1.count == b2.count);
    for (size_t i = 0; i < b1.count && i < b2.count; i++) {
        CHECK(b1.results[i].actor_id == b2.results[i].actor_id);
        CHECK(b1.results[i].score == b2.results[i].score);
    }
    batch_result_free(&b1);
    batch_result_free(&b2);
}

static void test_53_batch_inputs_not_modified(void)
{
    Actor a[FX_N];
    fx_actors(a);
    Actor a_snap[FX_N];
    memcpy(a_snap, a, sizeof a);
    ActorTag t1[N(FX_T1)], t2[N(FX_T2)], t3[N(FX_T3)], t4[N(FX_T4)], t5[N(FX_T5)];
    DemandTag dsnap[N(FX_D)];
    TagRelationship rsnap[N(FX_R)];
    memcpy(t1, FX_T1, sizeof t1); memcpy(t2, FX_T2, sizeof t2); memcpy(t3, FX_T3, sizeof t3);
    memcpy(t4, FX_T4, sizeof t4); memcpy(t5, FX_T5, sizeof t5);
    memcpy(dsnap, FX_D, sizeof dsnap); memcpy(rsnap, FX_R, sizeof rsnap);
    Demand d = mk_demand(FX_D, N(FX_D));
    Demand d_snap = d;
    RelationSet rs = mk_rels(FX_R, N(FX_R));
    BatchOptions o = { 0.3, 3 };
    MatchConfig cfg = { 0.25 }, cfg_snap = cfg;
    BatchOptions o_snap = o;

    BatchResult b;
    CHECK(batch_match(a, FX_N, &d, &rs, &cfg, &o, &b, NULL) == MATCHER_OK);
    batch_result_free(&b);

    o.top_k = 0; o_snap.top_k = 0;
    CHECK(batch_match(a, FX_N, &d, &rs, &cfg, &o, &b, NULL) == MATCHER_OK);
    batch_result_free(&b);

    CHECK(memcmp(a, a_snap, sizeof a) == 0);
    CHECK(memcmp(FX_T1, t1, sizeof t1) == 0 && memcmp(FX_T2, t2, sizeof t2) == 0);
    CHECK(memcmp(FX_T3, t3, sizeof t3) == 0 && memcmp(FX_T4, t4, sizeof t4) == 0);
    CHECK(memcmp(FX_T5, t5, sizeof t5) == 0);
    CHECK(memcmp(FX_D, dsnap, sizeof dsnap) == 0 && memcmp(FX_R, rsnap, sizeof rsnap) == 0);
    CHECK(memcmp(&d, &d_snap, sizeof d) == 0);
    CHECK(cfg.desirable_share == cfg_snap.desirable_share);
    CHECK(o.threshold == o_snap.threshold && o.top_k == o_snap.top_k);
}

static void alloc_failure_sweep(const BatchOptions *opt)
{
    Actor a[FX_N];
    fx_actors(a);
    Demand d = mk_demand(FX_D, N(FX_D));
    RelationSet rs = mk_rels(FX_R, N(FX_R));
    int failures_seen = 0;
    int reached_ok = 0;
    for (long n = 1; n <= 200; n++) {
        BatchResult b;
        int64_t bad = 0;
        ame_test_fail_nth_alloc(n);
        MatcherError e = batch_match(a, FX_N, &d, &rs, NULL, opt, &b, &bad);
        ame_test_fail_nth_alloc(0);
        if (e == MATCHER_OK) {
            CHECK(b.count == FX_N || opt->top_k > 0 || opt->threshold > 0.0);
            batch_result_free(&b);
            reached_ok = 1;
            break;
        }
        failures_seen++;
        CHECK(e == MATCHER_ERR_NO_MEMORY);
        CHECK(b.results == NULL && b.count == 0 && b.evaluated_count == 0);
        batch_result_free(&b);
    }
    CHECK(failures_seen >= 3);
    CHECK(reached_ok == 1);
}

static void test_54_batch_allocation_failure(void)
{
    BatchOptions unlimited = batch_default_options();
    BatchOptions limited = { 0.0, 2 };
    BatchOptions filtered = { 0.5, BATCH_TOP_K_UNLIMITED };
    alloc_failure_sweep(&unlimited);
    alloc_failure_sweep(&limited);
    alloc_failure_sweep(&filtered);

    ActorTag at[] = { { AI, 1.0 } };
    DemandTag dt[] = { REQ(AI, 1.0) };
    Actor a = mk_actor(at, 1);
    Demand d = mk_demand(dt, 1);
    MatchResult r;
    ame_test_fail_nth_alloc(1);
    CHECK(matcher_run(&a, &d, NULL, NULL, &r) == MATCHER_ERR_NO_MEMORY);
    ame_test_fail_nth_alloc(0);
    CHECK(r.details == NULL && r.score == 0.0);
    match_result_free(&r);
}

static void test_55_batch_errors(void)
{
    Actor a[FX_N];
    fx_actors(a);
    Demand d = mk_demand(FX_D, N(FX_D));
    RelationSet rs = mk_rels(FX_R, N(FX_R));
    BatchResult b;
    int64_t bad = 0;

    BatchOptions o1 = { -0.1, 0 }, o2 = { 1.1, 0 }, o3 = { NAN, 0 };
    CHECK(batch_match(a, FX_N, &d, &rs, NULL, &o1, &b, NULL) == MATCHER_ERR_INVALID_OPTIONS);
    CHECK(b.results == NULL && b.count == 0);
    CHECK(batch_match(a, FX_N, &d, &rs, NULL, &o2, &b, NULL) == MATCHER_ERR_INVALID_OPTIONS);
    CHECK(batch_match(a, FX_N, &d, &rs, NULL, &o3, &b, NULL) == MATCHER_ERR_INVALID_OPTIONS);

    MatchConfig badcfg = { 2.0 };
    CHECK(batch_match(a, FX_N, &d, &rs, &badcfg, NULL, &b, NULL) == MATCHER_ERR_INVALID_CONFIG);

    CHECK(batch_match(a, FX_N, &d, &rs, NULL, NULL, NULL, NULL) == MATCHER_ERR_NULL_ARG);
    CHECK(batch_match(a, FX_N, NULL, &rs, NULL, NULL, &b, NULL) == MATCHER_ERR_NULL_ARG);
    CHECK(batch_match(NULL, 3, &d, &rs, NULL, NULL, &b, NULL) == MATCHER_ERR_NULL_ARG);
    RelationSet rnull = { NULL, 2 };
    CHECK(batch_match(a, FX_N, &d, &rnull, NULL, NULL, &b, NULL) == MATCHER_ERR_NULL_ARG);

    DemandTag dup[] = { REQ(AI, 1.0), REQ(AI, 1.0) };
    Demand dd = mk_demand(dup, 2);
    CHECK(batch_match(NULL, 0, &dd, NULL, NULL, NULL, &b, NULL) == MATCHER_ERR_DUPLICATE_TAG);

    Actor dupa[3] = { a[0], a[1], a[0] };
    CHECK(batch_match(dupa, 3, &d, &rs, NULL, NULL, &b, &bad) == MATCHER_ERR_DUPLICATE_ACTOR);
    CHECK(bad == 1 && b.results == NULL);

    static ActorTag poisoned[] = { { AI, 2.0 } };
    Actor pa[FX_N];
    fx_actors(pa);
    pa[4].tags = poisoned; pa[4].tag_count = 1;
    bad = 0;
    CHECK(batch_match(pa, FX_N, &d, &rs, NULL, NULL, &b, &bad) == MATCHER_ERR_INVALID_WEIGHT);
    CHECK(bad == 5);
    CHECK(b.results == NULL && b.count == 0 && b.evaluated_count == 0);
    BatchOptions lim = { 0.0, 2 };
    CHECK(batch_match(pa, FX_N, &d, &rs, NULL, &lim, &b, &bad) == MATCHER_ERR_INVALID_WEIGHT);
    CHECK(bad == 5 && b.results == NULL);

    Demand empty = mk_demand(NULL, 0);
    CHECK(batch_match(a, FX_N, &empty, &rs, NULL, NULL, &b, NULL) == MATCHER_OK);
    CHECK(b.status == MATCH_STATUS_NOT_EVALUABLE);
    CHECK(b.count == 0 && b.results == NULL && b.evaluated_count == 0);
    batch_result_free(&b);
}

static void test_56_batch_free_idempotent(void)
{
    Actor a[FX_N];
    fx_actors(a);
    BatchResult b = fx_batch(a, FX_N, NULL);
    CHECK(b.results != NULL && b.count == FX_N);
    batch_result_free(&b);
    CHECK(b.results == NULL && b.count == 0);
    batch_result_free(&b);
    batch_result_free(NULL);
}

#define BIG_N 48
static void test_57_batch_large_population_consistency(void)
{
    static ActorTag store[BIG_N][4];
    Actor base[BIG_N];
    static const double wset[] = { 0.5, 1.0 };
    for (size_t i = 0; i < BIG_N; i++) {
        static const int64_t pool[4] = { AI, PYTHON, ML, LLM };
        size_t n = 0;
        for (size_t t = 0; t < 4; t++) {
            if (rnd() % 2 == 0) {
                store[i][n].tag_id = pool[t];
                store[i][n].weight = wset[rnd() % 2];
                n++;
            }
        }
        base[i] = (Actor){ (int64_t)(100 + i), ACTOR_TYPE_SOLVER, ACTOR_STATUS_ACTIVE,
                           n > 0 ? store[i] : NULL, n };
    }
    Demand d = mk_demand(FX_D, N(FX_D));
    RelationSet rs = mk_rels(FX_R, N(FX_R));
    BatchResult ref;
    CHECK(batch_match(base, BIG_N, &d, &rs, NULL, NULL, &ref, NULL) == MATCHER_OK);
    CHECK(ref.count == BIG_N);

    for (size_t i = 1; i < ref.count; i++) {
        const MatchResult *p = &ref.results[i - 1], *q = &ref.results[i];
        CHECK(p->score >= q->score - 1e-9);
        if (fabs(p->score - q->score) < 1e-9) {
            CHECK(p->required_missing_count <= q->required_missing_count);
            if (p->required_missing_count == q->required_missing_count) CHECK(p->actor_id < q->actor_id);
        }
    }

    for (int round = 0; round < 25; round++) {
        Actor buf[BIG_N];
        memcpy(buf, base, sizeof buf);
        shuffle_actors(buf, BIG_N);
        BatchResult b;
        CHECK(batch_match(buf, BIG_N, &d, &rs, NULL, NULL, &b, NULL) == MATCHER_OK);
        CHECK(b.count == ref.count);
        for (size_t i = 0; i < b.count && i < ref.count; i++) {
            CHECK(b.results[i].actor_id == ref.results[i].actor_id);
        }
        batch_result_free(&b);
    }

    for (size_t k = 1; k <= BIG_N + 2; k++) {
        Actor buf[BIG_N];
        memcpy(buf, base, sizeof buf);
        shuffle_actors(buf, BIG_N);
        BatchOptions o = { 0.0, k };
        BatchResult b;
        CHECK(batch_match(buf, BIG_N, &d, &rs, NULL, &o, &b, NULL) == MATCHER_OK);
        size_t want = k < ref.count ? k : ref.count;
        CHECK(b.count == want);
        for (size_t i = 0; i < b.count && i < want; i++) {
            CHECK(b.results[i].actor_id == ref.results[i].actor_id);
        }
        batch_result_free(&b);
    }
    BatchOptions ot = { 0.6, 5 };
    BatchResult bt;
    CHECK(batch_match(base, BIG_N, &d, &rs, NULL, &ot, &bt, NULL) == MATCHER_OK);
    size_t expect_passed = 0;
    for (size_t i = 0; i < ref.count; i++) if (ref.results[i].score >= 0.6 - 1e-12) expect_passed++;
    CHECK(bt.passed_count == expect_passed);
    CHECK(bt.count == (expect_passed < 5 ? expect_passed : 5));
    for (size_t i = 0; i < bt.count; i++) CHECK(bt.results[i].actor_id == ref.results[i].actor_id);
    batch_result_free(&bt);
    batch_result_free(&ref);
}

int main(void)
{
    RUN(test_01_all_required_exact);
    RUN(test_02_some_required_missing);
    RUN(test_03_required_related);
    RUN(test_04_desirable_related);
    RUN(test_05_nothing_matches);
    RUN(test_06_extra_actor_tags_ignored);
    RUN(test_07_actor_tag_weight);
    RUN(test_08_demand_tag_weight);
    RUN(test_09_relation_weight);
    RUN(test_10_only_required);
    RUN(test_11_only_desirable);
    RUN(test_12_empty_demand);
    RUN(test_13_actor_without_tags);
    RUN(test_14_wrong_direction);
    RUN(test_15_exact_beats_related);
    RUN(test_16_best_relation_no_sum_order_independent);
    RUN(test_17_deterministic_tie_break);
    RUN(test_18_synonym_and_part_of);
    RUN(test_19_desirable_cannot_compensate_required);
    RUN(test_20_config_desirable_share);
    RUN(test_21_score_bounds);
    RUN(test_22_input_validation);
    RUN(test_23_free_is_idempotent);
    RUN(test_24_detail_ordering_and_metadata);
    RUN(test_25_spec_example_and_report);
    RUN(test_26_share_zero_score_is_R);
    RUN(test_27_share_one_score_is_R_times_D);
    RUN(test_28_required_perfect_desirable_absent);
    RUN(test_29_required_absent_desirable_perfect);
    RUN(test_30_actor_weight_zero);
    RUN(test_31_relation_weight_zero);
    RUN(test_32_demand_weight_dominance);
    RUN(test_33_demand_weight_zero_rejected);
    RUN(test_34_multiple_relations_all_permutations);
    RUN(test_35_extra_actor_tags_exactly_equal);
    RUN(test_36_extra_demand_tags_effect);
    RUN(test_37_match_class_truth_table);
    RUN(test_38_missing_iff_zero_coverage);
    RUN(test_40_batch_zero_actors);
    RUN(test_41_batch_single_actor);
    RUN(test_42_batch_several_sorted_matches_individual);
    RUN(test_43_batch_order_independent_of_input);
    RUN(test_44_batch_deterministic_ties);
    RUN(test_45_batch_tie_with_float_noise);
    RUN(test_46_batch_threshold);
    RUN(test_47_batch_threshold_float_boundary);
    RUN(test_48_batch_top_k);
    RUN(test_49_batch_threshold_and_top_k);
    RUN(test_50_batch_required_missing_preserved);
    RUN(test_51_batch_score_zero_and_one);
    RUN(test_52_batch_extra_actor_tags);
    RUN(test_53_batch_inputs_not_modified);
    RUN(test_54_batch_allocation_failure);
    RUN(test_55_batch_errors);
    RUN(test_56_batch_free_idempotent);
    RUN(test_57_batch_large_population_consistency);

    printf("\n%d checks, %d failed\n", g_checks, g_failed);
    return g_failed == 0 ? 0 : 1;
}
