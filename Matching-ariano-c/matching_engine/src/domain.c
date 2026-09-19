#include "domain.h"

const char *actor_type_name(ActorType t)
{
    switch (t) {
    case ACTOR_TYPE_SOLVER:            return "SOLVER";
    case ACTOR_TYPE_STARTUP:           return "STARTUP";
    case ACTOR_TYPE_ORGANIZATION:      return "ORGANIZATION";
    case ACTOR_TYPE_GOVERNMENT_AGENCY: return "GOVERNMENT_AGENCY";
    }
    return "UNKNOWN";
}

const char *tag_type_name(TagType t)
{
    switch (t) {
    case TAG_TYPE_REQUIRED:  return "REQUIRED";
    case TAG_TYPE_DESIRABLE: return "DESIRABLE";
    }
    return "UNKNOWN";
}

const char *match_type_name(MatchType t)
{
    switch (t) {
    case MATCH_MISSING: return "MISSING";
    case MATCH_RELATED: return "RELATED";
    case MATCH_EXACT:   return "EXACT";
    }
    return "UNKNOWN";
}

const char *match_class_name(MatchClass c)
{
    switch (c) {
    case MATCH_CLASS_NONE:    return "NONE";
    case MATCH_CLASS_PARTIAL: return "PARTIAL";
    case MATCH_CLASS_RELATED: return "RELATED";
    case MATCH_CLASS_EXACT:   return "EXACT";
    }
    return "UNKNOWN";
}

const char *match_status_name(MatchStatus s)
{
    switch (s) {
    case MATCH_STATUS_EVALUATED:     return "EVALUATED";
    case MATCH_STATUS_NOT_EVALUABLE: return "NOT_EVALUABLE";
    }
    return "UNKNOWN";
}

const char *relation_type_name(RelationType t)
{
    switch (t) {
    case RELATION_NONE:    return "NONE";
    case RELATION_RELATED: return "RELATED";
    case RELATION_SYNONYM: return "SYNONYM";
    case RELATION_PART_OF: return "PART_OF";
    }
    return "UNKNOWN";
}

const char *tag_catalog_code(const TagCatalog *catalog, int64_t tag_id)
{
    if (catalog == NULL || catalog->items == NULL) {
        return NULL;
    }
    for (size_t i = 0; i < catalog->count; i++) {
        if (catalog->items[i].id == tag_id) {
            return catalog->items[i].code;
        }
    }
    return NULL;
}
