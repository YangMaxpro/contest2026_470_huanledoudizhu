#!/usr/bin/env python3
"""Check the replacement HAL contract with injected thread-creation failure."""
import pathlib
import subprocess
import sys
import tempfile

source = pathlib.Path(sys.argv[1]).resolve()
test = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>
#include "rtsa_hal_thread.c"
static int result, calls;
static uint32_t stack;
static void *seen_arg;
static void (*seen_entry)(void *);
static void entry(void *arg) { (void)arg; }
int rtsa_agora_create_thread(uint32_t *handle, uint8_t priority,
                            const char *name, void (*func)(void *),
                            uint32_t size, void *arg)
{
  assert(priority == 2 && name);
  calls++; stack = size; seen_arg = arg; seen_entry = func;
  if (!result) *handle = 42;
  return result;
}
int main(void)
{
  struct { const char *name; unsigned char untouched[32]; } context;
  const char *names[] = {"LTWP1", "RTCCB", "IOT", "IOT_CB", "other"};
  uint32_t sizes[] = {4096, 10240, 5120, 5120, 12288};
  memset(context.untouched, 0xa5, sizeof(context.untouched));
  for (unsigned int i = 0; i < sizeof(sizes)/sizeof(sizes[0]); i++)
    {
      uint32_t handle = 99;
      context.name = names[i]; result = 0;
      assert(k_os_thread_create(&handle, entry, &context) == 0);
      assert(handle == 42 && stack == sizes[i]);
      assert(seen_entry == entry && seen_arg == &context);
      result = -ENOMEM; handle = 99;
      assert(k_os_thread_create(&handle, entry, &context) == -ENOMEM);
      assert(handle == 0);
      for (unsigned int j = 0; j < sizeof(context.untouched); j++)
        assert(context.untouched[j] == 0xa5);
    }
  int old_calls = calls;
  uint32_t handle = 99;
  assert(k_os_thread_create(NULL, entry, &context) == -EINVAL);
  assert(k_os_thread_create(&handle, NULL, &context) == -EINVAL && handle == 0);
  assert(k_os_thread_create(&handle, entry, NULL) == -EINVAL);
  context.name = NULL;
  assert(k_os_thread_create(&handle, entry, &context) == -EINVAL);
  assert(calls == old_calls);
}
'''
with tempfile.TemporaryDirectory(prefix="rtsa-hal-thread-") as tmp:
    src = pathlib.Path(tmp) / "test.c"
    exe = pathlib.Path(tmp) / "test"
    src.write_text(test)
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-I" + str(source.parent), str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=15)
print("PASS RTSA HAL thread: failure propagation, original context/entry, stack selection")
