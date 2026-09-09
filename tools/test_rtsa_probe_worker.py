#!/usr/bin/env python3
"""Probe lifecycle tests: defer the independent task until command returns."""
import pathlib
import subprocess
import sys
import tempfile

source = pathlib.Path(sys.argv[1]).resolve()
test = r'''
#include <assert.h>
#include <pthread.h>
#include <stdlib.h>
#include <sys/types.h>
static int create_error, loop_error, allocation_error, sdk_calls, freed;
static char memory[1024];
static int (*pending_task)(int, char **);
static pid_t fake_task_create(const char *, int, int,
                             int (*)(int, char **), char *const *);
#define task_create fake_task_create
#define main probe_command
#include "rtsa_probe_main.c"
#undef main
#undef task_create
int rtsa_loopback_ready(void) { return loop_error; }
void *bk7258_psram_malloc(size_t n) { assert(n == 1024); return allocation_error ? NULL : memory; }
void bk7258_psram_free(void *p) { assert(p == memory); freed++; }
uint32_t bk7258_psram_heap_used(void) { return 64; }
int rtsa_sdk_smoke(const char *id) { assert(strlen(id) == 32); sdk_calls++; return 0; }
static pid_t fake_task_create(const char *name, int priority, int stack,
                             int (*entry)(int, char **), char *const *args)
{
  assert(!strcmp(name, "rtsa_lifecycle"));
  assert(stack == 16384 && priority == 90 && args == NULL);
  if (create_error) { errno = create_error; return -1; }
  assert(!pending_task);
  pending_task = entry;
  return 42;
}
int main(int argc, char **argv)
{
  assert(argc == 2);
  int scenario = atoi(argv[1]);
  char *status[] = {"rtsa_probe", "status"};
  char *bad[] = {"rtsa_probe", "init", "not-a-key"};
  char *start[] = {"rtsa_probe", "init", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"};
  assert(probe_command(2, status) == 0);
  assert(probe_command(3, bad) == 1 && !g_attempted);
  if (scenario == 1) create_error = ENOMEM;
  if (scenario == 2) loop_error = -ENODEV;
  if (scenario == 3) allocation_error = 1;
  assert(probe_command(3, start) == (scenario == 1 ? 1 : 0));
  if (scenario == 1)
    { assert(!g_attempted && !g_running && !pending_task && g_result == -ENOMEM); create_error = 0;
      assert(probe_command(3, start) == 0); }
  /* The command has exited, but the separate task has not run yet. */
  assert(g_attempted && g_running && g_step == RTSA_STEP_QUEUED);
  assert(sdk_calls == 0 && pending_task);
  assert(probe_command(3, start) == 1);
  assert(probe_command(2, status) == 0);
  assert(pending_task(0, NULL) == 0);
  assert(!g_running);
  assert(g_attempted && g_step == RTSA_STEP_DONE);
  assert(sdk_calls == (scenario < 2 ? 1 : 0));
  assert(freed == (scenario < 2 ? 1 : 0));
  assert(g_result == (scenario == 2 ? -ENODEV : scenario == 3 ? -ENOMEM : 0));
  assert(probe_command(3, start) == 1);
  assert(probe_command(2, status) == 0);
  assert(atomic_load(&g_trace_count) == 0);
  rtsa_cleanup_trace("disabled", 0, 0, 0);
  assert(atomic_load(&g_trace_count) == 0);
  atomic_store(&g_trace_cleanup, true);
  errno = EBUSY;
  for (int i = 0; i < 513; i++) rtsa_cleanup_trace("test", 0, 0, 0);
  assert(atomic_load(&g_trace_count) == 513 && errno == EBUSY);
  atomic_store(&g_trace_cleanup, false);
}
'''
with tempfile.TemporaryDirectory(prefix="rtsa-worker-") as tmp:
    root = pathlib.Path(tmp)
    config = root / "nuttx/config.h"
    config.parent.mkdir(parents=True)
    config.write_text("#define CONFIG_PTHREAD_MUTEX_TYPES 1\n#define CONFIG_NET_LOOPBACK 1\n")
    psram = root / "arch/chip/bk7258_psram.h"
    psram.parent.mkdir(parents=True)
    psram.write_text("#include <stddef.h>\n#include <stdint.h>\nvoid *bk7258_psram_malloc(size_t);\nvoid bk7258_psram_free(void *);\nuint32_t bk7258_psram_heap_used(void);\n")
    src, exe = root / "test.c", root / "test"
    src.write_text(test)
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-pthread",
                    "-I"+str(root), "-I"+str(source.parent), str(src), "-o", str(exe)], check=True)
    for case in range(4):
        subprocess.run([str(exe), str(case)], check=True, timeout=15, stdout=subprocess.DEVNULL)
print("PASS RTSA worker: deferred independent task, validation, priority/stack, preflight, failed launch, once-per-boot guard")
