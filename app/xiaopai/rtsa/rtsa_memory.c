/* SPDX-License-Identifier: Apache-2.0 */
#include <arch/chip/bk7258_psram.h>
#include <stddef.h>
#include "rtsa_trace.h"

/* Keep SDK allocations and reallocations on one dedicated heap. */
void *rtsa_psram_malloc_debug(const char *function, int line, size_t size, int flag)
{
  (void)function; (void)line; (void)flag;
  return bk7258_psram_malloc(size);
}

void rtsa_os_free_debug(const char *function, int line, void *ptr)
{
  (void)function; (void)line;
  RTSA_TRACE("free begin", ptr, 0);
  bk7258_psram_free(ptr);
}

void *rtsa_realloc(void *ptr, size_t size)
{
  return bk7258_psram_realloc(ptr, size);
}
