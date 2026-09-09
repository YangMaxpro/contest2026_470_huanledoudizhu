#!/usr/bin/env python3
"""Test the dedicated AP allocator lifecycle with mapped host memory."""
import pathlib
import subprocess
import sys
import tempfile

chip = pathlib.Path(sys.argv[1])
code = (chip / "bk7258_psram.c").read_text()
code = "\n".join(line for line in code.splitlines()
                 if not line.startswith("#include") and "__asm__" not in line)
stub = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#define BK7258_AP_PSRAM_HEAP_BASE 0x60720000u
#define BK7258_AP_PSRAM_HEAP_SIZE 0x002e0000u
typedef int mutex_t;
#define NXMUTEX_INITIALIZER 0
static void nxmutex_lock(mutex_t *m) { assert(!*m); *m=1; }
static void nxmutex_unlock(mutex_t *m) { assert(*m); *m=0; }
struct mm_heap_s { int dummy; };
struct info { unsigned uordblks; };
static struct mm_heap_s heap;
static unsigned used;
static struct mm_heap_s *mm_initialize(const char *name,void *p,size_t n)
{ assert(name && (uintptr_t)p==BK7258_AP_PSRAM_HEAP_BASE && n==BK7258_AP_PSRAM_HEAP_SIZE); return &heap; }
static void mm_uninitialize(struct mm_heap_s *h) { assert(h==&heap && !used); }
static void *mm_malloc(struct mm_heap_s *h,size_t n)
{ assert(h==&heap); if(n>320000)return NULL; used++; return (void *)(BK7258_AP_PSRAM_HEAP_BASE+128); }
static void mm_free(struct mm_heap_s *h,void *p)
{ assert(h==&heap && used && (uintptr_t)p==BK7258_AP_PSRAM_HEAP_BASE+128); used--; }
static void *mm_realloc(struct mm_heap_s *h,void *p,size_t size)
{ assert(h==&heap && used); return size>320000 ? NULL : p; }
static struct info mm_mallinfo(struct mm_heap_s *h)
{ assert(h==&heap); return (struct info){used}; }
'''
test = r'''
int main(void) {
  void *p=mmap((void *)BK7258_AP_PSRAM_HEAP_BASE,BK7258_AP_PSRAM_HEAP_SIZE,
              PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0);
  assert(p!=(void *)-1);
  assert(!bk7258_psram_malloc(10));
  assert(bk7258_psram_initialize()==0);
  assert(bk7258_psram_initialize()==0);
  assert(!bk7258_psram_malloc(0));
  assert(!bk7258_psram_malloc(320001));
  void *a=bk7258_psram_malloc(320000); assert(a);
  assert(bk7258_psram_heap_used()==1);
  assert(bk7258_psram_shutdown()==-EBUSY);
  assert(bk7258_psram_realloc(a,160000)==a);
  assert(bk7258_psram_realloc(a,320001)==NULL && used==1);
  assert(bk7258_psram_realloc((void *)1,32)==NULL && used==1);
  bk7258_psram_free(a); bk7258_psram_free(NULL);
  a=bk7258_psram_realloc(NULL,32); assert(a && used==1);
  assert(bk7258_psram_realloc(a,0)==NULL && !used);
  assert(bk7258_psram_shutdown()==0);
  assert(!bk7258_psram_malloc(10));
  assert(bk7258_psram_initialize()==0);
  bk7258_psram_power_lost(); assert(!bk7258_psram_malloc(10));
  assert(!g_lock && !g_allocations);
  assert(munmap(p,BK7258_AP_PSRAM_HEAP_SIZE)==0);
  puts("PASS dedicated PSRAM lifecycle, bounds, allocation failure and busy shutdown");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    src = pathlib.Path(tmp) / "test.c"
    exe = pathlib.Path(tmp) / "test"
    src.write_text(stub + code + test)
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                    str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
