#!/usr/bin/env python3
"""Lifecycle logic tests with a fake SDK; ARM build separately checks real ABI."""
import pathlib
import subprocess
import sys
import tempfile

source = pathlib.Path(sys.argv[1]).resolve()
header = r'''
#include <stdint.h>
typedef uint32_t connection_id_t;
typedef struct { void (*on_error)(connection_id_t, int, const char *); } agora_rtc_event_handler_t;
typedef struct {
  uint32_t area_code;
  struct { bool log_disable; bool log_disable_desensitize; } log_cfg;
  char padding[78];
  char license_value[33];
} rtc_service_option_t;
#define AREA_CODE_GLOB 0xffffffffu
int agora_rtc_init(const char *, const agora_rtc_event_handler_t *, rtc_service_option_t *);
int agora_rtc_create_connection(connection_id_t *);
int agora_rtc_destroy_connection(connection_id_t);
int agora_rtc_fini(void);
'''
test = r'''
#include <assert.h>
#include "rtsa_probe_sdk.c"
static int fails, calls, steps, callback_error;
void rtsa_probe_step(int stage, int result) { (void)result; steps = steps * 10 + stage; }
void rtsa_probe_error(int error) { callback_error = error; }
int agora_rtc_init(const char *app, const agora_rtc_event_handler_t *events, rtc_service_option_t *options)
{
  assert(!strcmp(app, "test-public-app-id"));
  assert(options->log_cfg.log_disable && !options->log_cfg.log_disable_desensitize);
  assert(!options->license_value[0]);
  calls = calls * 10 + 1;
  events->on_error(1, -17, "must-not-log");
  return fails == 1 ? -1 : 0;
}
int agora_rtc_create_connection(connection_id_t *connection)
{ calls = calls * 10 + 2; *connection = 42; return fails == 2 ? -2 : 0; }
int agora_rtc_destroy_connection(connection_id_t connection)
{ assert(connection == 42); calls = calls * 10 + 3; return fails == 3 ? -3 : 0; }
int agora_rtc_fini(void)
{ calls = calls * 10 + 4; return fails == 4 ? -4 : 0; }
int main(void)
{
  for (int i = 0; i <= 4; i++)
    {
      fails = i; calls = steps = callback_error = 0;
      assert(rtsa_sdk_smoke("test-public-app-id") == -i);
      assert(calls == (i == 1 ? 1 : i == 2 ? 124 : 1234));
      assert(steps == (i == 1 ? 2 : i == 2 ? 2385 : 23485));
      assert(callback_error == -17);
    }
}
'''
with tempfile.TemporaryDirectory(prefix="rtsa-probe-") as tmp:
    root = pathlib.Path(tmp)
    (root / "agora_rtc_api.h").write_text(header)
    src, exe = root / "test.c", root / "test"
    src.write_text(test)
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-I"+str(root), "-I"+str(source.parent), str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=15)
print("PASS RTSA probe: init/create/destroy/fini ordering, failure cleanup, sanitized callback")
