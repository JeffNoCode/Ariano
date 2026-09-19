/* report.h - Impressao legivel de um MatchResult (depuracao/CLI). */
#ifndef ARIANO_REPORT_H
#define ARIANO_REPORT_H

#include <stdio.h>
#include "domain.h"

/* `catalog` pode ser NULL; nesse caso os IDs sao impressos no lugar dos codigos. */
void match_result_print(FILE *out, const MatchResult *result, const TagCatalog *catalog);

#endif
