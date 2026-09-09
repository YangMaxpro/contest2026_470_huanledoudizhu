#!/usr/bin/env python3
"""Exercise the actual shim with deliberately unaligned vendor storage."""
import pathlib
import subprocess
import sys
import tempfile

source = pathlib.Path(sys.argv[1]).resolve()
test = r'''
#include <assert.h>
#include <stdio.h>
int k_raw_rwlock_trywrlock(void *lock) { (void)lock; return 1; }
void k_lock_unlock(void *slot) { (void)slot; }
void ahpl_usleep(unsigned int milliseconds, unsigned int microseconds)
{ (void)milliseconds; (void)microseconds; }
#include "rtsa_sync.c"
static unsigned char lockbuf[102], condbuf[98];
static int ready;
static void *worker(void *unused) {
  (void)unused;
  assert(!rtsa_pthread_mutex_lock(lockbuf+1));
  ready=1;
  assert(!rtsa_pthread_cond_signal(condbuf+1));
  assert(!rtsa_pthread_mutex_unlock(lockbuf+1));
  return NULL;
}
int main(int argc, char **argv) {
  if (argc == 2 && !strcmp(argv[1], "lock-failure")) {
    unsigned char uninitialized[sizeof(void *)] = {0};
    k_lock_lock(uninitialized);
    return 1;
  }
  int32_t attr;
  memset(lockbuf,0xa5,sizeof(lockbuf)); memset(condbuf,0x5a,sizeof(condbuf));
  assert(!rtsa_pthread_mutexattr_init(&attr));
  assert(!rtsa_pthread_mutexattr_settype(&attr,2));
  assert(!rtsa_pthread_mutex_init(lockbuf+1,&attr));
  assert(!rtsa_pthread_mutex_lock(lockbuf+1));
  assert(!rtsa_pthread_mutex_trylock(lockbuf+1));
  assert(!rtsa_pthread_mutex_unlock(lockbuf+1));
  assert(!rtsa_pthread_mutex_unlock(lockbuf+1));
  assert(!rtsa_pthread_mutex_destroy(lockbuf+1));
  assert(rtsa_pthread_mutex_destroy(lockbuf+1)==EINVAL);
  assert(!rtsa_pthread_mutex_init(lockbuf+1,NULL));
  assert(!rtsa_pthread_cond_init(condbuf+1,NULL));
  assert(!rtsa_pthread_mutex_lock(lockbuf+1));
  int32_t deadline[]={0,0,0,0};
  assert(rtsa_pthread_cond_timedwait(condbuf+1,lockbuf+1,deadline)==ETIMEDOUT);
  deadline[2]=-1;
  assert(rtsa_pthread_cond_timedwait(condbuf+1,lockbuf+1,deadline)==EINVAL);
  pthread_t thread; assert(!pthread_create(&thread,NULL,worker,NULL));
  while(!ready)assert(!rtsa_pthread_cond_wait(condbuf+1,lockbuf+1));
  assert(!rtsa_pthread_mutex_unlock(lockbuf+1));
  assert(!pthread_join(thread,NULL));
  assert(!rtsa_pthread_cond_broadcast(condbuf+1));
  assert(!rtsa_pthread_cond_destroy(condbuf+1));
  assert(!rtsa_pthread_mutex_destroy(lockbuf+1));
  assert(lockbuf[0]==0xa5 && lockbuf[101]==0xa5);
  assert(condbuf[0]==0x5a && condbuf[97]==0x5a);
  for(size_t i=1+sizeof(void *);i<101;i++)assert(lockbuf[i]==0xa5);
  for(size_t i=1+sizeof(void *);i<97;i++)assert(condbuf[i]==0x5a);
}
'''
with tempfile.TemporaryDirectory() as tmp:
    src = pathlib.Path(tmp) / "test.c"
    exe = pathlib.Path(tmp) / "test"
    src.write_text(test)
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-pthread", "-I"+str(source.parent), str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=15)
    failure = subprocess.run([str(exe), "lock-failure"], capture_output=True,
                             text=True, timeout=15)
    assert failure.returncode < 0 and failure.returncode == -6
    assert "RTSA lock failure: tid=" in failure.stdout
    assert "slot=" in failure.stdout
    assert "handle=(nil)" in failure.stdout
    assert "error=22" in failure.stdout
    assert "caller=" in failure.stdout
print("PASS RTSA synchronization: recursion, wait/signal, timeout, lifecycle, unaligned storage, guards and fail-stop diagnostics")
