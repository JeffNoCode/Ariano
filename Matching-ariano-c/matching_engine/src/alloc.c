#include "alloc.h"

#include <stdlib.h>

#ifdef ARIANO_TESTING
static long g_fail_at = 0;
static long g_count   = 0;

void ame_test_fail_nth_alloc(long n)
{
    g_fail_at = n;
    g_count   = 0;
}

long ame_test_alloc_count(void)
{
    return g_count;
}
#endif

void *ame_calloc(size_t n, size_t size)
{
#ifdef ARIANO_TESTING
    g_count++;
    if (g_fail_at > 0 && g_count == g_fail_at) {
        return NULL;
    }
#endif
    return calloc(n, size);
}
