/* SPDX-License-Identifier: Apache-2.0 */
/* Private archive imports only. Experimental probe, not baseline firmware. */
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "rtsa_trace.h"
#ifdef CONFIG_XIAOPAI_RTSA_PROBE
#include <stdio.h>
#include <unistd.h>
#endif

struct rtsa_thread_start
{
  void (*entry)(void *);
  void *arg;
};

static int rtsa_task_entry(int argc, char *argv[])
{
  char *end;
  uintptr_t raw;
  struct rtsa_thread_start start;

  if (argc != 2 || !argv[1]) return -EINVAL;
  raw = strtoul(argv[1], &end, 16);
  if (!raw || *end != '\0') return -EINVAL;
  start = *(struct rtsa_thread_start *)raw;
  free((void *)raw);
  start.entry(start.arg);
  return 0;
}

int rtsa_agora_create_thread(uint32_t *handle, uint8_t priority,
                              const char *name, void (*entry)(void *),
                              uint32_t stack_size, void *arg)
{
  char argument[2 + sizeof(uintptr_t) * 2 + 1];
  char *argv[] = {"rtsa", argument, NULL};
  int pid;
  (void)name;
  (void)priority;
  if (!handle) return -EINVAL;
  *handle = 0;
  if (!entry || stack_size > 65536) return -EINVAL;
  if (stack_size < 4096) stack_size = 4096;
#ifdef CONFIG_XIAOPAI_RTSA_PROBE
  printf("RTSA task create: stack=%lu native_priority=100\n",
         (unsigned long)stack_size);
  fflush(stdout);
  usleep(20000);
#endif
  struct rtsa_thread_start *start = malloc(sizeof(*start));
  if (!start) return -ENOMEM;
  start->entry = entry; start->arg = arg;
  snprintf(argument, sizeof(argument), "%p", (void *)start);
  pid = task_create(name, 100, stack_size, rtsa_task_entry, argv);
  if (pid < 0)
    {
      int error = errno;
      free(start);
      return -error;
    }
  *handle = (uint32_t)pid;
#ifdef CONFIG_XIAOPAI_RTSA_PROBE
  printf("RTSA task create returned: result=0 pid=%d\n", pid);
  fflush(stdout);
#endif
  return 0;
}

uint32_t rtsa_xTaskGetCurrentTaskHandle(void)
{
  return (uint32_t)getpid();
}

int rtsa_rtos_delete_thread(void *handle)
{
  /* Beken uses vTaskDelete(NULL) here. Do not turn this into pthread_exit():
   * pthread TLS destructors run after the SDK global teardown. */
  if (handle) return -ENOTSUP;
  RTSA_TRACE("task-delete", getpid(), 0);
  task_delete(0);
  return 0;
}

uint32_t rtsa_rtos_get_time(void)
{
  struct timespec ts;
  if (clock_gettime(CLOCK_MONOTONIC, &ts)) abort();
  return (uint32_t)((uint64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
}

int rtsa_clock_gettime(int clock, void *result)
{
  struct timespec ts;
  if (!result || (clock != 0 && clock != 1)) { errno = EINVAL; return -1; }
  int ret = clock_gettime(clock ? CLOCK_MONOTONIC : CLOCK_REALTIME, &ts);
  if (!ret)
    {
      int64_t seconds = ts.tv_sec;
      int32_t nanos = ts.tv_nsec;
      memset(result, 0, 16);
      memcpy(result, &seconds, 8);
      memcpy((char *)result + 8, &nanos, 4);
    }
  return ret;
}

int *rtsa_errno(void) { return &errno; }
