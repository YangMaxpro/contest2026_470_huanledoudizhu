#!/usr/bin/env python3
"""Compile real CP/AP random drivers with host hardware/transport stubs."""
import pathlib
import re
import subprocess
import sys
import tempfile


def source(path):
    return re.sub(r'^\s*#include[^\n]*', '', pathlib.Path(path).read_text(),
                  flags=re.M)


def run(code):
    with tempfile.TemporaryDirectory(prefix="xiaopai-rng-") as tmp:
        p = pathlib.Path(tmp)
        (p / "test.c").write_text(code)
        subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=undefined", str(p / "test.c"),
                        "-o", str(p / "test")], check=True)
        subprocess.run([str(p / "test")], check=True)


common = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
#include <syslog.h>
'''

cp_stubs = r'''
typedef int bk_err_t;
typedef int trng_hal_t;
#define BK_OK 0
#define BK_ERR_TRNG_DRIVER_NOT_INIT -1
#define TRNG_RETURN_ON_NOT_INIT_UNUSED 0
#define os_memset memset
#define RAND_MAX 0x7fffffff
static int locked, starts, stops, discards, reads, max_reads;
static uint32_t value = 0x80000000;
#define GLOBAL_INT_DECLARATION() int irq_level
#define GLOBAL_INT_DISABLE() do { irq_level = locked; locked = 1; } while (0)
#define GLOBAL_INT_RESTORE() do { locked = irq_level; } while (0)
static void trng_hal_init(trng_hal_t *h) { *h = 0; }
static void trng_hal_start_common(trng_hal_t *h)
{ (void)h; assert(locked); starts++; reads = 0; }
static void trng_hal_stop_common(trng_hal_t *h)
{ (void)h; assert(locked); stops++; if (reads > max_reads) max_reads = reads; }
static uint32_t trng_hal_get_random_number(trng_hal_t *h)
{ (void)h; assert(locked); reads++; return ++value; }
static void bk_delay_us(unsigned n)
{ assert(locked && n == 50); discards++; }
'''
cp_main = r'''
int main(void)
{
  uint8_t out[70];
  uint32_t first;
  memset(out, 0xa5, sizeof(out));
  assert(bk_fill_rand(out, 32) < 0 && !locked && starts == 0);
  assert(bk_trng_driver_init() == 0);
  assert(bk_fill_rand(NULL, 32) < 0);
  assert(bk_fill_rand(out, 0) < 0);
  assert(bk_fill_rand(out + 1, 65) == 0);
  assert(starts == 3 && stops == 3 && discards == 3 && !locked);
  memcpy(&first, out + 1, 4);
  assert(first == 0x80000011u); /* 16 discarded words; high bit retained */
  assert(out[0] == 0xa5 && out[66] == 0xa5);
  assert(max_reads == 24); /* 16 discarded + at most 8 returned */
  assert(bk_rand() >= 0 && starts == 4 && stops == 4 && !locked);
  puts("CP TRNG: init failure, warm-up, full width, chunk bound, tails, IRQ restore passed");
}
'''

ap_stubs = r'''
typedef int mutex_t;
#define NXMUTEX_INITIALIZER 0
static int calls, mode, locked, transport_ret;
static int nxmutex_lock(mutex_t *m)
{ (void)m; assert(!locked); locked = 1; return 0; }
static void nxmutex_unlock(mutex_t *m) { (void)m; locked = 0; }
struct file { int unused; };
struct file_operations { ssize_t (*read)(struct file *, char *, size_t); };
static int register_driver(const char *n, const struct file_operations *o,
                           int modebits, void *p)
{ (void)p; assert(!strcmp(n,"/dev/random") && o->read && modebits == 0444); return 0; }
static int bk7258_wifi_random_block(void *b, size_t n)
{
  uint8_t *p = b;
  size_t i;
  assert(locked && n == 32);
  calls++;
  if (transport_ret) return transport_ret;
  for (i = 0; i < n; i++) p[i] = mode == 1 ? 0 : (uint8_t)(i + (mode == 2 ? 0 : calls));
  return 0;
}
'''
ap_main = r'''
int main(void)
{
  char out[40];
  memset(out, 0x55, sizeof(out));
  devrandom_register();
  assert(bk7258_random_read(NULL, out, 0) == 0 && calls == 0);
  transport_ret = -ETIMEDOUT;
  assert(bk7258_random_read(NULL, out, 32) == -ETIMEDOUT && !locked);
  assert(out[0] == 0x55);
  transport_ret = 0;
  assert(bk7258_random_read(NULL, out + 1, 33) == 32);
  assert(out[0] == 0x55 && out[33] == 0x55);
  assert(bk7258_random_read(NULL, out, 1) == 1);
  mode = 2;
  assert(bk7258_random_read(NULL, out, 32) == 32);
  memset(out, 0x55, sizeof(out));
  assert(bk7258_random_read(NULL, out, 32) == -EIO && out[0] == 0x55);
  int saved = calls;
  assert(bk7258_random_read(NULL, out, 32) == -EIO && calls == saved);
  g_failed = false; g_have_previous = false; mode = 1;
  assert(bk7258_random_read(NULL, out, 32) == -EIO && out[0] == 0x55);
  puts("AP random: short reads, timeout, constant/repeated blocks, sticky failure passed");
}
'''

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_cp_random.py CP_TRNG_DRIVER AP_RANDOM_DRIVER")
    run(common + cp_stubs + source(sys.argv[1]) + cp_main)
    run(common + ap_stubs + source(sys.argv[2]) + ap_main)
