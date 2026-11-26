#include "matcher.h"

#include "alloc.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

static bool is_unit_weight(double w)     { return isfinite(w) && w >= 0.0 && w <= 1.0; }
static bool is_positive_weight(double w) { return isfinite(w) && w > 0.0; }
static bool is_valid_tag_id(int64_t id)  { return id > 0; }

MatcherError matcher_validate_config(const MatchConfig *cfg)
{
    if (cfg == NULL) {
        return MATCHER_ERR_NULL_ARG;
    }
    if (!isfinite(cfg->desirable_share) || cfg->desirable_share < 0.0 ||
        cfg->desirable_share > 1.0) {
        return MATCHER_ERR_INVALID_CONFIG;
    }
    return MATCHER_OK;
}

static MatcherError validate_actor(const Actor *a)
{
    if (a->tag_count > 0 && a->tags == NULL) {
        return MATCHER_ERR_NULL_ARG;
    }
    for (size_t i = 0; i < a->tag_count; i++) {
        if (!is_valid_tag_id(a->tags[i].tag_id)) {
            return MATCHER_ERR_INVALID_TAG_ID;
        }
        if (!is_unit_weight(a->tags[i].weight)) {
            return MATCHER_ERR_INVALID_WEIGHT;
        }
        for (size_t j = 0; j < i; j++) {
            if (a->tags[j].tag_id == a->tags[i].tag_id) {
                return MATCHER_ERR_DUPLICATE_TAG;
            }
        }
    }
    return MATCHER_OK;
}

static MatcherError validate_demand(const Demand *d, size_t *n_required, size_t *n_desirable)
{
    double weight_sum = 0.0;
    *n_required = 0;
    *n_desirable = 0;
    if (d->tag_count > 0 && d->tags == NULL) {
        return MATCHER_ERR_NULL_ARG;
    }
    for (size_t i = 0; i < d->tag_count; i++) {
        const DemandTag *t = &d->tags[i];
        if (!is_valid_tag_id(t->tag_id)) {
            return MATCHER_ERR_INVALID_TAG_ID;
        }
        if (t->type != TAG_TYPE_REQUIRED && t->type != TAG_TYPE_DESIRABLE) {
            return MATCHER_ERR_INVALID_TAG_TYPE;
        }
        if (!is_positive_weight(t->weight)) {
            return MATCHER_ERR_INVALID_WEIGHT;
        }
        weight_sum += t->weight;
        if (!isfinite(weight_sum)) {
            return MATCHER_ERR_INVALID_WEIGHT;
        }
        for (size_t j = 0; j < i; j++) {
            if (d->tags[j].tag_id == t->tag_id) {
                return MATCHER_ERR_DUPLICATE_TAG;
            }
        }
        if (t->type == TAG_TYPE_REQUIRED) {
            (*n_required)++;
        } else {
            (*n_desirable)++;
        }
    }
    return MATCHER_OK;
}

MatcherError matcher_validate_demand(const Demand *d)
{
    size_t nr, nd;
    if (d == NULL) {
        return MATCHER_ERR_NULL_ARG;
    }
    return validate_demand(d, &nr, &nd);
}

static const ActorTag *find_actor_tag(const Actor *a, int64_t tag_id)
{
    for (size_t i = 0; i < a->tag_count; i++) {
        if (a->tags[i].tag_id == tag_id) {
            return &a->tags[i];
        }
    }
    return NULL;
}

static bool relation_is_matchable(RelationType t)
{
    return t == RELATION_RELATED || t == RELATION_SYNONYM;
}

static bool is_better_candidate(double cov, int64_t src, RelationType type,
                                double best_cov, int64_t best_src, RelationType best_type)
{
    if (cov != best_cov) {
        return cov > best_cov;
    }
    if (src != best_src) {
        return src < best_src;
    }
    return type == RELATION_SYNONYM && best_type != RELATION_SYNONYM;
}

static MatcherError evaluate_tag(const Actor *actor, const RelationSet *rels,
                                 const DemandTag *dt, MatchDetail *out)
{
    MatchDetail d = {
        .demand_tag_id   = dt->tag_id,
        .tag_type        = dt->type,
        .match           = MATCH_MISSING,
        .actor_tag_id    = TAG_ID_NONE,
        .relation_type   = RELATION_NONE,
        .demand_weight   = dt->weight,
        .actor_weight    = 0.0,
        .relation_weight = 0.0,
        .coverage        = 0.0
    };

    const ActorTag *own = find_actor_tag(actor, dt->tag_id);
    if (own != NULL && own->weight > 0.0) {
        d.match           = MATCH_EXACT;
        d.actor_tag_id    = own->tag_id;
        d.actor_weight    = own->weight;
        d.relation_weight = 1.0;
        d.coverage        = own->weight;
        *out = d;
        return MATCHER_OK;
    }

    if (rels != NULL) {
        const ActorTag        *best_at  = NULL;
        const TagRelationship *best_rel = NULL;
        double                 best_cov = -1.0;

        for (size_t i = 0; i < rels->count; i++) {
            const TagRelationship *r = &rels->items[i];
            if (r->target_tag_id != dt->tag_id || !relation_is_matchable(r->type)) {
                continue;
            }
            if (!is_unit_weight(r->weight)) {
                return MATCHER_ERR_INVALID_WEIGHT;
            }
            const ActorTag *at = find_actor_tag(actor, r->source_tag_id);
            if (at == NULL) {
                continue;
            }
            double cov = at->weight * r->weight;
            if (!(cov > 0.0)) {
                continue;
            }
            if (best_rel == NULL ||
                is_better_candidate(cov, r->source_tag_id, r->type,
                                    best_cov, best_rel->source_tag_id, best_rel->type)) {
                best_at  = at;
                best_rel = r;
                best_cov = cov;
            }
        }

        if (best_rel != NULL) {
            d.match           = MATCH_RELATED;
            d.actor_tag_id    = best_at->tag_id;
            d.relation_type   = best_rel->type;
            d.actor_weight    = best_at->weight;
            d.relation_weight = best_rel->weight;
            d.coverage        = best_cov;
        }
    }

    *out = d;
    return MATCHER_OK;
}

static double clamp01(double x)
{
    if (x < 0.0) return 0.0;
    if (x > 1.0) return 1.0;
    return x;
}

static double group_score(const MatchDetail *d, size_t n)
{
    double num = 0.0, den = 0.0;
    for (size_t i = 0; i < n; i++) {
        num += d[i].demand_weight * d[i].coverage;
        den += d[i].demand_weight;
    }
    return (den > 0.0) ? clamp01(num / den) : 0.0;
}

static MatchClass classify(const MatchDetail *d, size_t n)
{
    size_t exact = 0, related = 0;
    for (size_t i = 0; i < n; i++) {
        if (d[i].match == MATCH_EXACT)        exact++;
        else if (d[i].match == MATCH_RELATED) related++;
    }
    if (exact == n)           return MATCH_CLASS_EXACT;
    if (exact + related == n) return MATCH_CLASS_RELATED;
    if (exact + related > 0)  return MATCH_CLASS_PARTIAL;
    return MATCH_CLASS_NONE;
}

const char *matcher_algorithm_version(void)
{
    return MATCHER_ALGORITHM_VERSION;
}

MatchConfig matcher_default_config(void)
{
    MatchConfig c = { .desirable_share = 0.20 };
    return c;
}

MatcherError matcher_run(const Actor *actor, const Demand *demand,
                         const RelationSet *relations, const MatchConfig *config,
                         MatchResult *out)
{
    if (out == NULL) {
        return MATCHER_ERR_NULL_ARG;
    }
    memset(out, 0, sizeof *out);
    if (actor == NULL || demand == NULL) {
        return MATCHER_ERR_NULL_ARG;
    }
    if (relations != NULL && relations->count > 0 && relations->items == NULL) {
        return MATCHER_ERR_NULL_ARG;
    }

    const MatchConfig cfg = (config != NULL) ? *config : matcher_default_config();
    MatcherError err = matcher_validate_config(&cfg);
    if (err != MATCHER_OK) return err;

    err = validate_actor(actor);
    if (err != MATCHER_OK) return err;

    size_t n_req = 0, n_des = 0;
    err = validate_demand(demand, &n_req, &n_des);
    if (err != MATCHER_OK) return err;

    MatchResult r;
    memset(&r, 0, sizeof r);
    r.actor_id          = actor->id;
    r.demand_id         = demand->id;
    r.algorithm_version = MATCHER_ALGORITHM_VERSION;

    if (demand->tag_count == 0) {
        r.status      = MATCH_STATUS_NOT_EVALUABLE;
        r.match_class = MATCH_CLASS_NONE;
        *out = r;
        return MATCHER_OK;
    }

    r.status = MATCH_STATUS_EVALUATED;
    r.details = ame_calloc(demand->tag_count, sizeof *r.details);
    if (r.details == NULL) {
        return MATCHER_ERR_NO_MEMORY;
    }

    size_t pos = 0;
    static const TagType order[2] = { TAG_TYPE_REQUIRED, TAG_TYPE_DESIRABLE };
    for (size_t g = 0; g < 2; g++) {
        for (size_t i = 0; i < demand->tag_count; i++) {
            if (demand->tags[i].type != order[g]) {
                continue;
            }
            err = evaluate_tag(actor, relations, &demand->tags[i], &r.details[pos]);
            if (err != MATCHER_OK) {
                free(r.details);
                return err;
            }
            pos++;
        }
    }

    r.required_count  = n_req;
    r.desirable_count = n_des;
    const MatchDetail *req = r.details;
    const MatchDetail *des = r.details + n_req;

    for (size_t i = 0; i < n_req; i++) {
        if (req[i].match == MATCH_MISSING) r.required_missing_count++;
    }

    r.required_score  = group_score(req, n_req);
    r.desirable_score = group_score(des, n_des);

    if (n_req > 0 && n_des > 0) {
        r.score = r.required_score *
                  ((1.0 - cfg.desirable_share) + cfg.desirable_share * r.desirable_score);
    } else if (n_req > 0) {
        r.score = r.required_score;
    } else {
        r.score = r.desirable_score;
    }
    r.score = clamp01(r.score);

    r.match_class = (n_req > 0) ? classify(req, n_req) : classify(des, n_des);

    *out = r;
    return MATCHER_OK;
}

void match_result_free(MatchResult *result)
{
    if (result == NULL) {
        return;
    }
    free(result->details);
    memset(result, 0, sizeof *result);
}

const MatchDetail *match_result_required(const MatchResult *r)
{
    return (r != NULL && r->required_count > 0) ? r->details : NULL;
}

const MatchDetail *match_result_desirable(const MatchResult *r)
{
    return (r != NULL && r->desirable_count > 0) ? r->details + r->required_count : NULL;
}

const char *matcher_strerror(MatcherError err)
{
    switch (err) {
    case MATCHER_OK:                    return "ok";
    case MATCHER_ERR_NULL_ARG:          return "null argument";
    case MATCHER_ERR_INVALID_CONFIG:    return "invalid config";
    case MATCHER_ERR_INVALID_TAG_ID:    return "invalid tag id (must be > 0)";
    case MATCHER_ERR_INVALID_WEIGHT:    return "invalid weight";
    case MATCHER_ERR_INVALID_TAG_TYPE:  return "invalid tag type";
    case MATCHER_ERR_DUPLICATE_TAG:     return "duplicate tag";
    case MATCHER_ERR_NO_MEMORY:         return "out of memory";
    case MATCHER_ERR_INVALID_OPTIONS:   return "invalid batch options";
    case MATCHER_ERR_DUPLICATE_ACTOR:   return "duplicate actor id";
    }
    return "unknown error";
}
