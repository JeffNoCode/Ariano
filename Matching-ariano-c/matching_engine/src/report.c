#include "report.h"
#include "matcher.h"

static void print_tag(FILE *out, const TagCatalog *cat, int64_t id)
{
    const char *code = tag_catalog_code(cat, id);
    if (code != NULL) {
        fputs(code, out);
    } else {
        fprintf(out, "<tag#%lld>", (long long)id);
    }
}

static void print_group(FILE *out, const char *title, const MatchDetail *d, size_t n,
                        const TagCatalog *cat)
{
    fprintf(out, "%s:\n", title);
    if (n == 0 || d == NULL) {
        fputs("    (none)\n", out);
        return;
    }
    for (size_t i = 0; i < n; i++) {
        fputs("    ", out);
        print_tag(out, cat, d[i].demand_tag_id);
        switch (d[i].match) {
        case MATCH_EXACT:
            fputs(" <- ", out);
            print_tag(out, cat, d[i].actor_tag_id);
            fprintf(out, "  [EXACT]  actor_w=%.2f demand_w=%.2f\n",
                    d[i].actor_weight, d[i].demand_weight);
            break;
        case MATCH_RELATED:
            fputs(" <- ", out);
            print_tag(out, cat, d[i].actor_tag_id);
            fprintf(out, "  [RELATED/%s]  actor_w=%.2f relation_w=%.2f demand_w=%.2f\n",
                    relation_type_name(d[i].relation_type), d[i].actor_weight,
                    d[i].relation_weight, d[i].demand_weight);
            break;
        case MATCH_MISSING:
            fprintf(out, " <- (none)  [MISSING]  demand_w=%.2f\n", d[i].demand_weight);
            break;
        }
    }
}

void match_result_print(FILE *out, const MatchResult *r, const TagCatalog *cat)
{
    if (out == NULL || r == NULL) {
        return;
    }
    fprintf(out, "Actor %lld | Demand %lld | algorithm %s\n", (long long)r->actor_id,
            (long long)r->demand_id, r->algorithm_version ? r->algorithm_version : "?");
    fprintf(out, "Status: %s\n", match_status_name(r->status));
    fprintf(out, "Score: %.4f  (class=%s, required=%.4f, desirable=%.4f, required_missing=%zu)\n",
            r->score, match_class_name(r->match_class), r->required_score,
            r->desirable_score, r->required_missing_count);
    print_group(out, "Required", match_result_required(r), r->required_count, cat);
    print_group(out, "Desirable", match_result_desirable(r), r->desirable_count, cat);
}
