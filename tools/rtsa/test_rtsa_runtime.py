#!/usr/bin/env python3
"""No RTC/cloud: exercise runtime boundaries and detached thread cleanup."""
import pathlib
import subprocess
import sys
import tempfile

source = pathlib.Path(sys.argv[1]).resolve()
test = r'''
#include <assert.h>
#include <semaphore.h>
#include "rtsa_runtime.c"
static sem_t started, done;
static uint32_t self;
static void callback(void *arg) {
  assert(arg==&done);
  self=rtsa_xTaskGetCurrentTaskHandle();
  sem_post(&started);
  sem_wait(&done);
}
int main(void) {
  unsigned char output[18]; memset(output,0xa5,sizeof(output));
  assert(!rtsa_clock_gettime(0,output+1));
  int64_t seconds; int32_t nanos;
  memcpy(&seconds,output+1,8); memcpy(&nanos,output+9,4);
  assert(seconds>1700000000 && nanos>=0 && nanos<1000000000);
  assert(output[0]==0xa5 && output[17]==0xa5);
  assert(!rtsa_clock_gettime(1,output+1));
  assert(rtsa_clock_gettime(2,output+1)==-1 && errno==EINVAL);
  assert(rtsa_clock_gettime(0,NULL)==-1 && errno==EINVAL);
  uint32_t before=rtsa_rtos_get_time(); struct timespec ts={0,2000000}; nanosleep(&ts,NULL);
  assert((uint32_t)(rtsa_rtos_get_time()-before)<1000);
  assert(rtsa_rtos_delete_thread(&done)==-ENOTSUP);
  assert(!sem_init(&started,0,0) && !sem_init(&done,0,0));
  uint32_t handle;
  assert(rtsa_agora_create_thread(&handle,2,"test",callback,65537,&done)==-EINVAL);
  assert(!rtsa_agora_create_thread(&handle,2,"test",callback,65536,&done));
  assert(!sem_wait(&started)); assert(handle==self); assert(!sem_post(&done));
  /* Process teardown owns detached-thread completion; no firmware claim. */
}
'''
with tempfile.TemporaryDirectory() as tmp:
    src = pathlib.Path(tmp) / "test.c"
    exe = pathlib.Path(tmp) / "test"
    src.write_text(test)
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                    "-pthread", "-I"+str(source.parent), str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=15)
print("PASS RTSA runtime: time ABI, guards, thread creation/identity and unsupported-delete rejection")
