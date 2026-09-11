#!/usr/bin/env python3
"""Compile heartbeat and the real mailbox wait loop with fault-injection stubs."""
import pathlib
import re
import subprocess
import sys
import tempfile


def strip_includes(text):
    return re.sub(r'^\s*#include[^\n]*', '', text, flags=re.M)


def main():
    chip = pathlib.Path(sys.argv[1])
    heartbeat = strip_includes((chip / 'bk7258_ipc_heartbeat.c').read_text())
    heartbeat = heartbeat.replace('__asm__ volatile("dmb sy" ::: "memory");', '')
    mailbox = (chip / 'bk7258_mailbox_channel.c').read_text()
    wait = mailbox[mailbox.index('static int wait_channel('):
                   mailbox.index('/****************************************************************************',
                                 mailbox.index('static int wait_channel('))]
    headers = strip_includes((chip / 'include/bk7258_heartbeat.h').read_text())
    headers += strip_includes((chip / 'include/bk7258_netstats.h').read_text())
    stubs = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <time.h>
#include <setjmp.h>
#include <stdarg.h>
#define OK 0
#define MSEC2TICK(n) ((n) / 10)
#define TICK2MSEC(n) ((uint64_t)(n) * 10)
#define BK7258_MB_CHAN_HW_CTRL_TX 0
#define BK7258_MB_CHAN_PWC_TX 1
#define MB_CHANNEL_COUNT 2
#define NXMUTEX_INITIALIZER 0
#define LOG_ERR 3
typedef int mutex_t;
typedef int irqstate_t;
typedef long sclock_t;
static uint32_t host_payload;
#define BK7258_IPC_TX_ADDRESS ((uintptr_t)&host_payload)
struct bk7258_mb_wire_message
{
  unsigned header, reserved;
  uintptr_t payload_address;
  unsigned payload_length;
};
static struct { bool queued; int result; } g_channels[2];
static clock_t ticks;
static int irq_depth, mutex_locked, mode, writes, dumps, sends;
static int worker_cycles;
static bool runtime;
static jmp_buf worker_exit;
static int (*worker_entry)(int, char **);
static clock_t clock_systime_ticks(void) { return ticks; }
static irqstate_t up_irq_save(void) { return irq_depth++; }
static void up_irq_restore(irqstate_t f) { irq_depth = f; }
static int nxmutex_lock(mutex_t *m)
{ (void)m; assert(!mutex_locked); mutex_locked = 1; return 0; }
static void nxmutex_unlock(mutex_t *m)
{ (void)m; assert(mutex_locked); mutex_locked = 0; }
static unsigned channel_index(uint8_t c) { return c; }
static void bk7258_mbox_kick_rx(void) {}
static void bk7258_mailbox_dump_stats(void)
{ assert(!runtime); dumps++; }
static int blocked_console(const char *fmt, ...)
{ (void)fmt; assert(!runtime); writes++; return 0; }
#define printf blocked_console
#define syslog(level, ...) blocked_console(__VA_ARGS__)
static int nxsig_usleep(unsigned us)
{
  assert(!irq_depth);
  if (us == 2000000 && worker_cycles-- == 0) longjmp(worker_exit, 1);
  ticks += (us + 9999) / 10000;
  return 0;
}
static int kthread_create(const char *name, int pri, int stack,
                          int (*entry)(int, char **), char **argv)
{
  assert(!strcmp(name, "ipc-heartbeat") && pri == 110 && stack == 1536);
  (void)argv; worker_entry = entry; return mode == 5 ? -ENOMEM : 8;
}
static int bk7258_mailbox_send_wire(unsigned ch,
  const struct bk7258_mb_wire_message *msg,
  void (*cb)(const struct bk7258_mb_wire_message *, int, void *), void *arg)
{
  struct bk7258_mb_wire_message ack = { .reserved = 2 };
  assert(ch == 0 && msg->payload_address == (uintptr_t)&host_payload);
  assert(msg->payload_length == (msg->header == 2 ? 4u : 0u));
  sends++;
  if (mode == 1) return -EBUSY;
  g_channels[ch].queued = mode == 2;
  g_channels[ch].result = mode == 2 ? -EINPROGRESS : 0;
  if (mode != 2)
    {
      irqstate_t f = up_irq_save();
      if (mode == 3) ack.reserved = 0;
      cb(mode == 4 ? NULL : &ack, 0, arg);
      up_irq_restore(f);
    }
  return 0;
}
'''
    counters = r'''
void bk7258_mailbox_fill_counters(struct bk7258_net_counters *c)
{
  assert(irq_depth);
  c->mb_tx = sends; c->mb_rx = 7; c->mb_timeout = 3; c->mb_bad_ack = 2;
  c->mb_recovery_cycle = 1; c->mb_link_down = 1; c->mb_link_state = 4;
}
'''
    tests = r'''
int main(void)
{
  struct bk7258_heartbeat_status s;
  bk7258_heartbeat_get_status(NULL);
  bk7258_heartbeat_get_status(&s);
  assert(!s.started && !s.attempts && !s.since_ack_ms);
  mode = 5;
  assert(bk7258_ipc_heartbeat_start() == -ENOMEM);
  bk7258_heartbeat_get_status(&s);
  assert(!s.started);
  mode = 0;
  assert(bk7258_ipc_heartbeat_start() == 0 && worker_entry);
  assert(bk7258_ipc_heartbeat_start() == 0);
  bk7258_heartbeat_get_status(&s);
  assert(s.started && s.attempts == 1 && s.acknowledgements == 1);
  runtime = true; /* Any diagnostic/printf here fails instead of hanging. */
  for (mode = 1; mode <= 4; mode++)
    {
      int before = sends;
      worker_cycles = 3;
      if (setjmp(worker_exit) == 0) worker_entry(0, NULL);
      assert(sends == before + 3 && !irq_depth && !mutex_locked);
    }
  bk7258_heartbeat_get_status(&s);
  assert(s.attempts == 13 && s.failures == 12 && s.acknowledgements == 1);
  assert(s.last_result == -EREMOTEIO && !s.sending);
  assert(s.max_send_ms == 600 && s.max_attempt_gap_ms == 2600);
  assert(s.mailbox_tx == (unsigned)sends && s.mailbox_timeouts == 3);
  mode = 0;
  worker_cycles = 3;
  if (setjmp(worker_exit) == 0) worker_entry(0, NULL);
  bk7258_heartbeat_get_status(&s);
  assert(s.attempts == 16 && s.acknowledgements == 4 && s.failures == 12);
  assert(s.last_result == 0 && s.since_ack_ms == 0 && s.since_attempt_ms == 0);
  assert(wait_channel(9, 600) == -EINVAL && dumps == 0);
  assert(writes == 1); /* Only startup output; no worker console writes. */
  runtime = false;
  g_channels[1].queued = true;
  assert(bk7258_mailbox_wait_pwc(600) == -ETIMEDOUT && dumps == 1);
  assert(!mutex_locked && !irq_depth);
  puts("heartbeat: blocked-console isolation, 600ms queue timeout, busy/bad/missing ACK, recovery, snapshots, startup failure passed");
}
'''
    with tempfile.TemporaryDirectory(prefix='xiaopai-heartbeat-') as tmp:
        root = pathlib.Path(tmp)
        (root / 'test.c').write_text(stubs + headers + counters + wait + heartbeat + tests)
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=undefined', str(root / 'test.c'),
                        '-o', str(root / 'test')], check=True)
        subprocess.run([str(root / 'test')], check=True)


if __name__ == '__main__':
    main()
