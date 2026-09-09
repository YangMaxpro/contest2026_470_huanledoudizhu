/* SPDX-License-Identifier: Apache-2.0 */
/* Newlib C-locale ABI for private SDK imports only. */
#include <arpa/inet.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

_Noreturn void rtsa_abort(void)
{
  /* Only private vendor imports are renamed; native abort remains intact. */
  printf("RTSA fatal: abort caller=%p\n", __builtin_return_address(0));
  fflush(stdout);
  usleep(20000);
  abort();
}

/* Newlib ctype.h: U=1 L=2 N=4 S=8 P=16 C=32 X=64 B=128.
 * The SDK relocates references to _ctype_+1; element zero represents EOF. */
#define CLASS(c) (((c) >= 'A' && (c) <= 'Z' ? 1 : 0) | \
                 ((c) >= 'a' && (c) <= 'z' ? 2 : 0) | \
                 ((c) >= '0' && (c) <= '9' ? 4 : 0) | \
                 ((c) == ' ' || ((c) >= 9 && (c) <= 13) ? 8 : 0) | \
                 (((c) >= 33 && (c) <= 47) || ((c) >= 58 && (c) <= 64) || \
                  ((c) >= 91 && (c) <= 96) || ((c) >= 123 && (c) <= 126) ? 16 : 0) | \
                 ((c) < 32 || (c) == 127 ? 32 : 0) | \
                 (((c) >= 'A' && (c) <= 'F') || ((c) >= 'a' && (c) <= 'f') ? 64 : 0) | \
                 ((c) == ' ' ? 128 : 0))
#define ROW(n) CLASS(n), CLASS(n+1), CLASS(n+2), CLASS(n+3), \
               CLASS(n+4), CLASS(n+5), CLASS(n+6), CLASS(n+7), \
               CLASS(n+8), CLASS(n+9), CLASS(n+10), CLASS(n+11), \
               CLASS(n+12), CLASS(n+13), CLASS(n+14), CLASS(n+15)
const unsigned char rtsa__ctype_[257] =
{
  0, ROW(0), ROW(16), ROW(32), ROW(48), ROW(64), ROW(80), ROW(96), ROW(112),
  ROW(128), ROW(144), ROW(160), ROW(176), ROW(192), ROW(208), ROW(224), ROW(240)
};
#undef ROW
#undef CLASS

uint32_t rtsa_ipaddr_addr(const char *text)
{
  return text ? inet_addr(text) : INADDR_NONE;
}

_Noreturn void rtsa___assert_func(const char *file, int line,
                                 const char *function, const char *expression)
{
  (void)file;
  (void)line;
  (void)function;
  (void)expression;
  printf("RTSA fatal: assertion caller=%p line=%d\n",
         __builtin_return_address(0), line);
  fflush(stdout);
  usleep(20000);
  abort();
}

_Noreturn void rtsa___wrap___assert_func(const char *file, int line,
                                        const char *function, const char *expression)
{
  rtsa___assert_func(file, line, function, expression);
}
