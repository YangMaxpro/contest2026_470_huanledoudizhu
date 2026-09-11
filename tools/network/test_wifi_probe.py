#!/usr/bin/env python3
"""Compile the real probe against synchronous mailbox fixtures on Linux.

Usage: python3 test_wifi_probe.py /path/to/nuttx/arch/arm/src/bk7258
This does not access a serial port or a board. It tests parsing/ownership,
not the hardware mailbox, RTOS scheduling or inter-core memory visibility.
"""

import pathlib
import subprocess
import sys
import tempfile

STUBS = r'''
#define __VENDOR_BEKEN_CHIPS_BK7258_HARDWARE_BK7258_MBOX_H
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#define OK 0
#define MSEC2TICK(x) (x)
#define NXMUTEX_INITIALIZER 0
#define SEM_INITIALIZER(x) (x)
#define BK7258_CP_RAM_START 0x28064000u
#define BK7258_CP_RAM_END 0x2809f700u
#define BK7258_MB_CHAN_WIFI_CMD_TX 0x14
#define BK7258_MB_CHAN_WIFI_CMD_RX 0x44
typedef int mutex_t;
typedef int sem_t;
typedef int irqstate_t;
static int nxmutex_lock(mutex_t *m) { (void)m; return 0; }
static int nxmutex_unlock(mutex_t *m) { (void)m; return 0; }
static int enter_critical_section(void) { return 0; }
static void leave_critical_section(int f) { (void)f; }
static int nxsem_trywait(sem_t *s)
{ if (*s) { --*s; return 0; } return -EAGAIN; }
static void nxsem_post(sem_t *s) { ++*s; }
static int nxsem_tickwait_uninterruptible(sem_t *s, int ticks)
{ (void)ticks; return nxsem_trywait(s) == 0 ? 0 : -ETIMEDOUT; }
struct bk7258_mb_wire_message { uint32_t words[4]; };
typedef void (*bk7258_mb_tx_complete_t)
  (const struct bk7258_mb_wire_message *, int, void *);
static bool mock_link = true;
static bool bk7258_mailbox_link_ready(void) { return mock_link; }
static int bk7258_mailbox_register_rx(uint8_t ch,
  int (*rx)(const struct bk7258_mb_wire_message *, uint8_t *, void *), void *arg)
{ assert(ch == 0x44); (void)rx; (void)arg; return 0; }
static int bk7258_mailbox_send_wire(uint8_t ch,
  const struct bk7258_mb_wire_message *m, bk7258_mb_tx_complete_t cb, void *arg);
'''

TESTS = r'''
enum { GOOD, LENGTH, SEQUENCE, TIMEOUT, REJECT, SEND_FAIL };
static int mode;
static int calls;

static int bk7258_mailbox_send_wire(uint8_t ch,
  const struct bk7258_mb_wire_message *m, bk7258_mb_tx_complete_t cb, void *arg)
{
  struct probe_slot_s *slot = arg;
  struct wifi_probe_node_s node;
  struct wifi_probe_cpdu_s *cpdu = (void *)(uintptr_t)(BK7258_CP_RAM_START+4);
  struct wifi_probe_event_s *event = (void *)(cpdu+1);
  uint8_t *data = (void *)(event+1);
  struct bk7258_mb_wire_message response;
  ++calls;
  assert(ch == 0x14);
  memcpy(&node, m, sizeof(node));
  assert(node.head == (uintptr_t)&slot->cpdu);
  assert(node.count == 1 && node.head == node.tail && node.channel == 0);
  assert(slot->pattern == WIFI_PROBE_BUSY && slot->pending);
  if (mode == SEND_FAIL) return -EBUSY;
  if (mode == TIMEOUT) return 0;
  if (mode == REJECT) { cb(NULL, -EREMOTEIO, arg); return 0; }
  memset(cpdu, 0, 256);
  event->id = slot->request.command | WIFI_PROBE_CONFIRM;
  event->sequence = slot->request.sequence + (mode == SEQUENCE);
  event->length = slot->request.command == WIFI_PROBE_GET_MAC ? 6 : 99;
  if (mode == LENGTH) --event->length;
  cpdu->length = sizeof(*cpdu) + sizeof(*event) + event->length;
  if (slot->request.command == WIFI_PROBE_GET_MAC) data[0] = 2;
  *(uint32_t *)(uintptr_t)BK7258_CP_RAM_START = WIFI_PROBE_BUSY;
  node.head = (uintptr_t)cpdu;
  node.tail = node.head;
  memcpy(&response, &node, sizeof(response));
  assert(probe_rx(&response, NULL, NULL) == 0);
  assert(*(uint32_t *)(uintptr_t)BK7258_CP_RAM_START == WIFI_PROBE_FREE);
  slot->pattern = WIFI_PROBE_FREE;
  cb(NULL, 0, arg);
  return 0;
}

int main(void)
{
  uint8_t mac[6];
  struct bk7258_mb_wire_message message;
  struct wifi_probe_node_s node = {0};
  struct wifi_probe_cpdu_s *cpdu = (void *)(uintptr_t)(BK7258_CP_RAM_START+4);
  struct wifi_probe_event_s *event = (void *)(cpdu+1);
  int prior;
  void *mapped = mmap((void *)(uintptr_t)BK7258_CP_RAM_START, 0x40000,
    PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE, -1, 0);
  assert(mapped == (void *)(uintptr_t)BK7258_CP_RAM_START);
  assert(bk7258_wifi_probe() == 0);
  assert(bk7258_wifi_probe() == 0);
  mode = LENGTH;
  assert(probe_request(WIFI_PROBE_GET_MAC, mac, 6) == -EPROTO);
  mode = SEQUENCE;
  assert(probe_request(WIFI_PROBE_GET_MAC, mac, 6) == -ETIMEDOUT);
  mode = REJECT;
  assert(probe_request(WIFI_PROBE_GET_MAC, mac, 6) == -EREMOTEIO);
  mode = SEND_FAIL;
  assert(probe_request(WIFI_PROBE_GET_MAC, mac, 6) == -EBUSY);
  mode = GOOD;
  assert(probe_request(WIFI_PROBE_GET_MAC, mac, 6) == 0);
  mock_link = false;
  prior = calls;
  assert(probe_request(WIFI_PROBE_GET_MAC, mac, 6) == -ENOLINK);
  assert(calls == prior);
  mock_link = true;

  /* Invalid lists must not write the ownership word. */
  *(uint32_t *)(uintptr_t)BK7258_CP_RAM_START = WIFI_PROBE_BUSY;
  node.head = (uintptr_t)cpdu;
  node.tail = node.head;
  node.count = 1;
  cpdu->next = node.head;
  memcpy(&message, &node, sizeof(message));
  assert(probe_rx(&message, NULL, NULL) == -EPROTO);
  cpdu->next = 0;
  node.tail += 4;
  memcpy(&message, &node, sizeof(message));
  assert(probe_rx(&message, NULL, NULL) == -EPROTO);
  node.tail = node.head;
  event->length = UINT16_MAX;
  memcpy(&message, &node, sizeof(message));
  assert(probe_rx(&message, NULL, NULL) == -EPROTO);
  node.head = BK7258_CP_RAM_END;
  node.tail = node.head;
  memcpy(&message, &node, sizeof(message));
  assert(probe_rx(&message, NULL, NULL) == -EPROTO);
  assert(*(uint32_t *)(uintptr_t)BK7258_CP_RAM_START == WIFI_PROBE_BUSY);

  mode = TIMEOUT;
  for (int i = 0; i < PROBE_SLOTS; i++)
    assert(probe_request(WIFI_PROBE_GET_MAC, mac, 6) == -ETIMEDOUT);
  prior = calls;
  assert(probe_request(WIFI_PROBE_GET_MAC, mac, 6) == -EBUSY);
  assert(calls == prior);
  /* Neither transport completion alone nor FREE alone permits reuse. */
  probe_tx_done(NULL, 0, &g_slots[0]);
  g_slots[1].pattern = WIFI_PROBE_FREE;
  assert(probe_request(WIFI_PROBE_GET_MAC, mac, 6) == -EBUSY);
  g_slots[0].pattern = WIFI_PROBE_FREE;
  mode = GOOD;
  assert(probe_request(WIFI_PROBE_GET_MAC, mac, 6) == 0);
  g_sequence = UINT16_MAX;
  assert(probe_request(WIFI_PROBE_GET_MAC, mac, 6) == -EOVERFLOW);
  munmap(mapped, 0x40000);
  puts("PASS: repeat probe, exact lengths, stale sequence, rejection, link down,");
  puts("malformed lists, timeout quarantine, delayed release, sequence overflow");
}
'''


def main():
    source_dir = pathlib.Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="wifi-probe-test-") as temp:
        work = pathlib.Path(temp)
        (work / "nuttx").mkdir()
        for header in ("config", "clock", "irq", "spinlock", "mutex", "semaphore"):
            (work / "nuttx" / (header + ".h")).write_text("")
        harness = work / "test.c"
        harness.write_text(STUBS + '\n#include "' +
                           str(source_dir / "bk7258_wifi_probe.c") +
                           '"\n' + TESTS)
        executable = work / "test"
        subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-fno-pie", "-no-pie", "-fsanitize=undefined",
                        "-I", str(work), str(harness), "-o", str(executable)],
                       check=True)
        subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    main()
