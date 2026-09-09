#!/usr/bin/env python3
"""Compile the actual CP receive function with host ownership fixtures.

Usage: python3 test_cp_ipv4_forwarding.py /path/to/cif_wifi_dp.c
Checks routing and pbuf release counts, not radio or mailbox hardware.
"""
import pathlib
import subprocess
import sys
import tempfile

STUB = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <arpa/inet.h>
#define CONFIG_CONTROLLER_RX_DIRECT_PSH 1
#define CONFIG_BRIDGE 0
#define CIF_LOGV(...) ((void)0)
#define BK_ASSERT assert
#define BK_OK 0
#define PBUF_RAW 0
#define PBUF_RAM_RX 0
#define NETIF_IF_STA 0
#define ETHTYPE_IP 0x0800
#define ETHTYPE_ARP 0x0806
#define ETHTYPE_EAPOL 0x888e
#define RX_MSDU_DATA 1
#define CIF_TASK_MSG_RX_DATA 1
typedef int bk_err_t;
typedef int16_t s16;
struct pbuf { void *payload; unsigned len, tot_len; };
struct cpdu_t { struct { unsigned length, type, need_free, special_type,
                         vif_idx, dst_index; } co_hdr; };
typedef struct cpdu_t cpdu_t;
struct eth_hdr { uint16_t type; };
static struct { bool no_host, host_wifi_init; } cif_env;
static struct { unsigned cif_rx_cnt; } stats;
#define cif_stats_ptr (&stats)
static int sends, frees, allocations, filter_calls, fail_send;
static struct pbuf *last_sent;
static struct pbuf *packet(void) {
  struct pbuf *p = calloc(1, sizeof(*p) + sizeof(cpdu_t) + 1600);
  assert(p); p->payload = (char *)(p+1) + sizeof(cpdu_t);
  p->len = p->tot_len = 64; return p;
}
static int wifi_netif_vif_to_netif_type(void *vif) { return (int)(uintptr_t)vif; }
static struct pbuf *pbuf_alloc(int layer, unsigned len, int type) {
  (void)layer; (void)len; (void)type; allocations++; return packet();
}
static void pbuf_header(struct pbuf *p, s16 size) { (void)p; (void)size; }
static void pbuf_free(struct pbuf *p) { frees++; free(p); }
static bool cif_is_arp_request(struct pbuf *p) { (void)p; return true; }
static bool cif_filter_check_ip_data(struct pbuf *p) {
  (void)p; filter_calls++; return true; /* CP-reserved DHCP/DNS */
}
static int cif_msg_sender(void *cpdu, int kind, int extra) {
  (void)kind; (void)extra; sends++;
  last_sent = ((struct pbuf *)cpdu)-1; return fail_send ? -1 : 0;
}
'''

TEST = r'''
static void check(unsigned eth, bool host, bool init, int vif,
                  bool failure, bool forwarded) {
  struct pbuf *p = packet();
  struct eth_hdr h = {.type = htons(eth)};
  cif_env.no_host = !host; cif_env.host_wifi_init = init;
  sends = frees = allocations = filter_calls = 0;
  fail_send = failure; last_sent = NULL;
  bool local = cif_rx_local_packet_check(&p, &h, (void *)(uintptr_t)vif, 0);
  if (forwarded) {
    assert(!local && sends == 1 && allocations == 0 && last_sent == p);
    assert(frees == (failure ? 1 : 0));
    assert(filter_calls == 0);
    if (!failure) free(last_sent); /* Simulate later AP recycle. */
  } else {
    assert(local && sends == 0 && frees == 0);
    free(p);
  }
}
int main(void) {
  check(ETHTYPE_EAPOL, true, true, 0, false, false);
  check(ETHTYPE_IP, false, true, 0, false, false);
  check(ETHTYPE_IP, true, false, 0, false, false);
  check(ETHTYPE_IP, true, true, 1, false, false);
  check(ETHTYPE_IP, true, true, 0, false, CONFIG_WIFI_VNET_AP_IPV4);
  check(ETHTYPE_IP, true, true, 0, true, CONFIG_WIFI_VNET_AP_IPV4);
#if CONFIG_WIFI_VNET_AP_IPV4
  check(ETHTYPE_ARP, true, true, 0, false, true);
  check(ETHTYPE_ARP, true, true, 0, true, true);
#endif
  return 0;
}
'''

source = pathlib.Path(sys.argv[1]).read_text()
start = source.index("bool cif_rx_local_packet_check(")
brace = source.index("{", start)
# The receive function is the final function in this vendor source.
function = source[start:]
if not function.rstrip().endswith("}"):
    raise ValueError("Unexpected source layout")
with tempfile.TemporaryDirectory() as directory:
    root = pathlib.Path(directory)
    fixture = root / "fixture.c"
    fixture.write_text(STUB + function + TEST)
    for mode in (0, 1):
        binary = root / f"test-{mode}"
        subprocess.run(["cc", "-std=gnu11", "-Wall", "-Werror",
                        f"-DCONFIG_WIFI_VNET_AP_IPV4={mode}",
                        str(fixture), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
print("PASS: STA IPv4/ARP ownership, CP EAPOL, other VIF, no-host, "
      "send failure and single release; legacy mode preserved")
