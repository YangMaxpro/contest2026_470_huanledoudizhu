/* SPDX-License-Identifier: Apache-2.0 */
/* Vendor 1.9.5.7 synchronization ABI. Enabled only in the experimental probe.
 * Archive imports must be renamed to these symbols, never global --wrap.
 * Explicit init/destroy only; concurrent destroy is invalid POSIX usage. */
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>
#include "rtsa_trace.h"

_Static_assert(sizeof(void *) <= 96, "vendor handle storage");

static void *load_handle(const void *slot)
{
  void *p = NULL;
  if (slot) memcpy(&p, slot, sizeof(p));
  return p;
}

static void save_handle(void *slot, void *p)
{
  memcpy(slot, &p, sizeof(p));
}

int rtsa_pthread_mutexattr_init(void *attr)
{
  int32_t type = 0;
  if (!attr) return EINVAL;
  memcpy(attr, &type, sizeof(type));
  return 0;
}

int rtsa_pthread_mutexattr_settype(void *attr, int type)
{
  int32_t value = type;
  if (!attr || type < 0 || type > 2) return EINVAL;
  memcpy(attr, &value, sizeof(value));
  return 0;
}

int rtsa_pthread_mutex_init(void *slot, const void *attr)
{
  pthread_mutexattr_t native;
  int32_t type = 0;
  int ret;
  if (!slot) return EINVAL;
  save_handle(slot, NULL);
  if (attr) memcpy(&type, attr, sizeof(type));
  if (type < 0 || type > 2) return EINVAL;
  pthread_mutex_t *p = malloc(sizeof(*p));
  if (!p) return ENOMEM;
  ret = pthread_mutexattr_init(&native);
  if (!ret)
    {
      ret = pthread_mutexattr_settype(&native, type == 2 ? PTHREAD_MUTEX_RECURSIVE :
                                     type == 1 ? PTHREAD_MUTEX_ERRORCHECK : PTHREAD_MUTEX_NORMAL);
      if (!ret) ret = pthread_mutex_init(p, &native);
      pthread_mutexattr_destroy(&native);
    }
  if (ret) free(p);
  else save_handle(slot, p);
  return ret;
}

int rtsa_pthread_mutex_lock(void *slot)
{
  pthread_mutex_t *p = load_handle(slot);
  return p ? pthread_mutex_lock(p) : EINVAL;
}

/* Preserve the vendor fail-stop contract, but retain the caller above its
 * generic k_lock_lock wrapper so teardown ordering errors are identifiable.
 */
void k_lock_lock(void *slot)
{
  void *handle = load_handle(slot);
  int result = handle ? pthread_mutex_lock(handle) : EINVAL;
  if (result)
    {
      /* Do not attempt recovery: the vendor implementation terminates here.
       * Capture the same handle passed to pthread_mutex_lock so a concurrent
       * invalid lifetime cannot make the diagnostic point at a later value.
       */
      printf("RTSA lock failure: tid=%lu slot=%p handle=%p error=%d caller=%p\n",
             (unsigned long)pthread_self(), slot, handle, result,
             __builtin_return_address(0));
      fflush(stdout);
      usleep(20000);
      abort();
    }
}

/* Vendor k_rwlock_wrlock protects its raw reader/writer state with a k_lock at
 * offset 104.  Preserve its retry sequence, but identify a destroyed guard
 * before k_lock_lock emits its generic fail-stop record. */
extern int k_raw_rwlock_trywrlock(void *lock);
extern void k_lock_unlock(void *slot);
extern void ahpl_usleep(uint32_t milliseconds, uint32_t microseconds);

void k_rwlock_wrlock(void *rwlock)
{
  void *guard = load_handle(rwlock);
  if (!guard)
    {
      printf("RTSA rwlock failure: tid=%lu rwlock=%p guard=%p caller=%p\n",
             (unsigned long)pthread_self(), rwlock, guard,
             __builtin_return_address(0));
      fflush(stdout);
    }

  for (;;)
    {
      k_lock_lock(rwlock);
      if (k_raw_rwlock_trywrlock((char *)rwlock + 104)) return;
      k_lock_unlock(rwlock);
      ahpl_usleep(10, 0);
    }
}

int rtsa_pthread_mutex_trylock(void *slot)
{
  pthread_mutex_t *p = load_handle(slot);
  return p ? pthread_mutex_trylock(p) : EINVAL;
}

int rtsa_pthread_mutex_unlock(void *slot)
{
  pthread_mutex_t *p = load_handle(slot);
  return p ? pthread_mutex_unlock(p) : EINVAL;
}

int rtsa_pthread_mutex_destroy(void *slot)
{
  RTSA_TRACE("mutex-destroy begin", slot, 0);
  pthread_mutex_t *p = load_handle(slot);
  if (!p) return EINVAL;
  int ret = pthread_mutex_destroy(p);
  if (!ret) { free(p); save_handle(slot, NULL); }
  RTSA_TRACE("mutex-destroy end", slot, ret);
  return ret;
}

int rtsa_pthread_cond_init(void *slot, const void *attr)
{
  int32_t value = 0;
  if (!slot) return EINVAL;
  save_handle(slot, NULL);
  if (attr) memcpy(&value, attr, sizeof(value));
  /* The vendor k_cond_init passes a zero/default attribute. */
  if (value != 0) return ENOTSUP;
  pthread_cond_t *p = malloc(sizeof(*p));
  if (!p) return ENOMEM;
  int ret = pthread_cond_init(p, NULL);
  if (ret) free(p);
  else save_handle(slot, p);
  return ret;
}

int rtsa_pthread_cond_signal(void *slot)
{
  pthread_cond_t *p = load_handle(slot);
  return p ? pthread_cond_signal(p) : EINVAL;
}

int rtsa_pthread_cond_broadcast(void *slot)
{
  pthread_cond_t *p = load_handle(slot);
  return p ? pthread_cond_broadcast(p) : EINVAL;
}

int rtsa_pthread_cond_wait(void *cond, void *mutex)
{
  RTSA_TRACE("cond-wait begin", cond, 0);
  pthread_cond_t *c = load_handle(cond);
  pthread_mutex_t *m = load_handle(mutex);
  int ret = c && m ? pthread_cond_wait(c, m) : EINVAL;
  RTSA_TRACE("cond-wait end", cond, ret);
  return ret;
}

int rtsa_pthread_cond_timedwait(void *cond, void *mutex, const void *deadline)
{
  /* Verified DWARF: time_t is 64-bit; tv_nsec is int32 at offset 8. */
  int64_t seconds;
  int32_t nanos;
  pthread_cond_t *c = load_handle(cond);
  pthread_mutex_t *m = load_handle(mutex);
  if (!c || !m || !deadline) return EINVAL;
  memcpy(&seconds, deadline, sizeof(seconds));
  memcpy(&nanos, (const char *)deadline + 8, sizeof(nanos));
  if (nanos < 0 || nanos >= 1000000000) return EINVAL;
  struct timespec ts = { .tv_sec = seconds, .tv_nsec = nanos };
  if ((int64_t)ts.tv_sec != seconds) return EOVERFLOW;
  return pthread_cond_timedwait(c, m, &ts);
}

int rtsa_pthread_cond_destroy(void *slot)
{
  RTSA_TRACE("cond-destroy begin", slot, 0);
  pthread_cond_t *p = load_handle(slot);
  if (!p) return EINVAL;
  int ret = pthread_cond_destroy(p);
  if (!ret) { free(p); save_handle(slot, NULL); }
  RTSA_TRACE("cond-destroy end", slot, ret);
  return ret;
}
