#!/usr/bin/env python3
"""Compile the real late-init sequence with ordered/failing service stubs."""
import pathlib
import subprocess
import sys
import tempfile

board, chip = map(pathlib.Path, sys.argv[1:3])


def function(text, signature):
    start = text.index(signature)
    opening = text.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


pwc = (chip / "bk7258_pm_pwc.c").read_text()
bootstrap = function(pwc, "int bk7258_pwc_start(void)")
assert "psram_power_set(" not in bootstrap
assert "bk7258_psram_initialize(" not in bootstrap
psram = function(pwc, "int bk7258_pwc_psram_start(void)")
late = function((board / "src/board_boot.c").read_text(),
                "void board_late_initialize(void)")
stub = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#define CONFIG_BK7258_PSRAM 1
#define CONFIG_BK7258_WIFI 1
#define PM_POWER_MODULE_STATE_ON 0
#define PM_POWER_MODULE_STATE_OFF 1
#define OK 0
static int step, mode, wifi, rollback;
static bool ready;
static int bk7258_pwc_start(void) { assert(step++==0); return 0; }
static int bk7258_ipc_heartbeat_start(void) { assert(step++==1); return 0; }
static int bk7258_mailbox_wait_link_ready(unsigned ms)
{ assert(step++==2 && ms==8000); if(mode==3)return -ETIMEDOUT; ready=true; return 0; }
static bool bk7258_mailbox_link_ready(void) { return ready; }
static void bk7258_mailbox_dump_stats(void) {}
static int psram_power_set(unsigned state)
{
  assert(ready);
  if(state==PM_POWER_MODULE_STATE_OFF) { rollback++; return 0; }
  assert(step++==3); return mode==1?-EIO:0;
}
static int bk7258_psram_initialize(void)
{ assert(step++==4 && ready); return mode==2?-EIO:0; }
static int bk7258_wifi_initialize(void) { assert(ready); wifi++; return 0; }
'''
test = r'''
int main(void) {
  assert(bk7258_pwc_psram_start()==-ENOLINK && step==0);
  for(mode=0;mode<4;mode++) {
    step=wifi=rollback=0; ready=false;
    board_late_initialize();
    if(mode==3)assert(step==3 && !wifi && !ready);
    else {
      assert(wifi==1 && ready);
      assert(step==(mode==1?4:5));
      assert(rollback==(mode==1 || mode==2));
    }
  }
  puts("PASS boot order: PWC, HW_CTRL, READY, PSRAM; PSRAM errors preserve Wi-Fi/console");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    src = pathlib.Path(tmp) / "test.c"
    exe = pathlib.Path(tmp) / "test"
    src.write_text(stub + psram + late + test)
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                    str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
