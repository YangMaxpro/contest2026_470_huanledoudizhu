/* SPDX-License-Identifier: Apache-2.0 */
#ifndef RTSA_TRACE_H
#define RTSA_TRACE_H
#include <stdint.h>

/* Optional diagnostic sink; standalone ABI tests do not link the probe. */
extern void rtsa_cleanup_trace(const char *event, uintptr_t object,
                               uintptr_t caller, int result)
  __attribute__((weak));
#define RTSA_TRACE(event, object, result) do { \
  if (rtsa_cleanup_trace) \
    rtsa_cleanup_trace(event, (uintptr_t)(object), \
                       (uintptr_t)__builtin_return_address(0), result); \
} while (0)
#endif
