/* SPDX-License-Identifier: Apache-2.0 */
#include <nuttx/config.h>
#include <arch/chip/bk7258_psram.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <stdatomic.h>
#include "rtsa_probe.h"

#if !defined(CONFIG_PTHREAD_MUTEX_TYPES) || !defined(CONFIG_NET_LOOPBACK)
#  error "RTSA lifecycle probe requires native recursive mutexes and loopback"
#endif

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static bool g_attempted;
static bool g_running;
static int g_step;
static int g_result;
static int g_callback_error;
static uint32_t g_heap_before;
static uint32_t g_heap_after;
static char g_app_id[33];
static atomic_bool g_trace_cleanup;
static atomic_uint g_trace_count;

void rtsa_cleanup_trace(const char *event, uintptr_t object,
                        uintptr_t caller, int result)
{
  if (!atomic_load(&g_trace_cleanup)) return;
  unsigned int count = atomic_fetch_add(&g_trace_count, 1);
  if (count >= 512) return;
  int saved_errno = errno;
  printf("RTSA cleanup #%u tid=%lu %s object=%lx caller=%lx result=%d\n",
         count, (unsigned long)pthread_self(), event,
         (unsigned long)object, (unsigned long)caller, result);
  fflush(stdout);
  if (count == 511) puts("RTSA cleanup trace limit reached");
  errno = saved_errno;
}

static void checkpoint(const char *name)
{
  printf("RTSA checkpoint: %s\n", name);
  fflush(stdout);
  /* Let the mailbox console drain before a potentially failing operation. */
  usleep(20000);
}

void rtsa_probe_step(int step, int result)
{
  if (step == RTSA_STEP_FINI) atomic_store(&g_trace_cleanup, true);
  pthread_mutex_lock(&g_lock);
  g_step = step;
  g_result = result;
  pthread_mutex_unlock(&g_lock);
  printf("RTSA checkpoint: SDK step=%d result=%d\n", step, result);
  fflush(stdout);
  usleep(20000);
  if (step == RTSA_STEP_HOLD)
    {
      checkpoint("cleanup pending; observing SDK workers for 5 seconds");
      for (int i = 0; i < 5; i++)
        {
          sleep(1);
          printf("RTSA observation: %d/5\n", i + 1);
          fflush(stdout);
        }
    }
}

void rtsa_probe_error(int error)
{
  pthread_mutex_lock(&g_lock);
  g_callback_error = error;
  pthread_mutex_unlock(&g_lock);
}

static int run_probe(int argc, char **argv)
{
  (void)argc;
  (void)argv;
  checkpoint("worker entered");
  rtsa_probe_step(RTSA_STEP_PREFLIGHT, 0);
  checkpoint("loopback check begin");
  int result = rtsa_loopback_ready();
  printf("RTSA checkpoint: loopback result=%d\n", result);
  if (!result)
    {
      checkpoint("PSRAM allocation begin");
      void *test = bk7258_psram_malloc(1024);
      if (!test) result = -ENOMEM;
      else
        {
          checkpoint("PSRAM free begin");
          bk7258_psram_free(test);
        }
    }
  checkpoint("heap snapshot begin");
  uint32_t before = bk7258_psram_heap_used();
  checkpoint("preflight finished");
  if (!result) result = rtsa_sdk_smoke(g_app_id);
  checkpoint("SDK returned; heap snapshot begin");
  uint32_t after = bk7258_psram_heap_used();
  pthread_mutex_lock(&g_lock);
  g_heap_before = before;
  g_heap_after = after;
  g_result = result;
  g_step = RTSA_STEP_DONE;
  g_running = false;
  pthread_mutex_unlock(&g_lock);
  return 0;
}

int main(int argc, char **argv)
{
  if (argc == 2 && !strcmp(argv[1], "status"))
    {
      static const char *names[] = {"idle", "preflight", "init", "create", "destroy", "fini", "done", "queued", "hold"};
      pthread_mutex_lock(&g_lock);
      bool attempted = g_attempted;
      bool running = g_running;
      int step = g_step;
      int result = g_result;
      int error = g_callback_error;
      uint32_t before = g_heap_before;
      uint32_t after = g_heap_after;
      pthread_mutex_unlock(&g_lock);
      printf("RTSA probe v44: attempted=%d running=%d stage=%s result=%d callback_error=%d\n",
             attempted, running, names[step], result, error);
      printf("PSRAM used bytes: before=%lu after=%lu; no channel join or audio\n",
             (unsigned long)before, (unsigned long)after);
      return 0;
    }
  if (argc != 3 || strcmp(argv[1], "init") || strlen(argv[2]) != 32)
    {
      puts("Usage: rtsa_probe status | init <32-hex-App-ID> (once per boot, no channel/audio)");
      return 1;
    }
  for (int i = 0; i < 32; i++)
    if (!((argv[2][i] >= '0' && argv[2][i] <= '9') ||
          (argv[2][i] >= 'a' && argv[2][i] <= 'f') ||
          (argv[2][i] >= 'A' && argv[2][i] <= 'F'))) return 1;

  pthread_mutex_lock(&g_lock);
  if (g_attempted)
    {
      pthread_mutex_unlock(&g_lock);
      puts("RTSA probe already attempted; inspect status, reboot before another SDK initialization");
      return 1;
    }
  memcpy(g_app_id, argv[2], sizeof(g_app_id));
  g_attempted = true;
  g_running = true;
  g_step = RTSA_STEP_QUEUED;
  pthread_mutex_unlock(&g_lock);

  /* A detached pthread still dies when this command's task group exits.
   * An independent task owns the SDK threads until smoke-test cleanup.
   */
  pid_t pid = task_create("rtsa_lifecycle", 90, 16384, run_probe, NULL);
  if (pid < 0)
    {
      int result = -errno;
      pthread_mutex_lock(&g_lock);
      g_running = false;
      g_attempted = false;
      g_result = result;
      pthread_mutex_unlock(&g_lock);
      printf("RTSA probe worker failed: %d\n", result);
      return 1;
    }
  puts("RTSA local lifecycle probe started; use rtsa_probe status and xiaopai ipc status");
  return 0;
}
