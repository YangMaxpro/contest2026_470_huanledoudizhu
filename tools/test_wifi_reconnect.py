#!/usr/bin/env python3
"""Compile actual STA connect/event functions with CP-command stubs."""
import pathlib
import sys
from test_cp_random import common, run, source

stubs = r'''
#define OK 0
#define WIFI_PACKET_QUEUE 4
#define IW_AUTH_WPA_VERSION_DISABLED 1
#define IW_AUTH_WPA_VERSION_WPA2 4
#define IW_AUTH_CIPHER_NONE 1
#define IW_AUTH_CIPHER_CCMP 8
typedef int irqstate_t;
typedef int netpkt_t;
struct netdev_lowerhalf_s {
  struct { struct { struct { uint8_t ether_addr_octet[6]; } ether; } d_mac; } netdev;
};
static struct {
  int packet_lock, role_sem;
  bool admin_up, tx_gate, ap_started;
  unsigned ap_client_count, role_epoch;
  enum wifi_role active_role, configured_role;
  enum wifi_role_state role_state;
  struct wifi_role_config sta_config, ap_config;
  struct netdev_lowerhalf_s lower;
  uint8_t sta_mac[6], ap_mac[6];
} g_wifi;
static int g_bk7258_driver_lock;
static int stop_calls, stop_result, command_calls, command_error, packet_locked;
static bool notified_carrier;
static int notifications;
static int nxmutex_lock(int *p) { (void)p; assert(!packet_locked); packet_locked = 1; return 0; }
static int nxmutex_unlock(int *p) { (void)p; assert(packet_locked); packet_locked = 0; return 0; }
static int rspin_lock_irqsave(int *p) { (void)p; return 0; }
static void rspin_unlock_irqrestore(int *p, int f) { (void)p; (void)f; }
static void nxsem_post(int *p) { (*p)++; }
static bool wifi_tx_busy(void) { return false; }
static int wifi_stop_active_role(void)
{
  stop_calls++;
  if (stop_result) return stop_result;
  g_wifi.active_role = WIFI_ROLE_NONE; g_wifi.role_state = WIFI_ROLE_IDLE;
  return 0;
}
static void wifi_role_deactivate(enum wifi_role role)
{ (void)role; g_wifi.active_role = WIFI_ROLE_NONE; g_wifi.role_state = WIFI_ROLE_IDLE; }
static int wifi_ap_status_query(struct bk7258_wifi_ap_status_response *s)
{ (void)s; return -ENOSYS; }
static void wifi_ap_start_event(bool v) { (void)v; }
static void wifi_set_carrier(bool v) { notified_carrier = v; }
static uint8_t wifi_rx_queue_take_locked(netpkt_t **p) { (void)p; return 0; }
static void wifi_rx_queue_free(netpkt_t **p, uint8_t n) { (void)p; assert(n == 0); }
static void wifi_notify_event(enum bk7258_wifi_event_e e, unsigned reason)
{ (void)e; (void)reason; notifications++; }
static int wifi_command(unsigned cmd, const void *p, size_t n,
                        void *out, size_t cap, uint16_t *len)
{
  (void)out; (void)cap; (void)len;
  command_calls++;
  if (cmd == BK7258_WIFI_CMD_SET_AUTO_RECONNECT)
    { assert(n == sizeof(bool) && *(const bool *)p); }
  else
    { assert(cmd == BK7258_WIFI_CMD_CONNECT && n == 97); }
  return command_error;
}
'''
tests = r'''
int main(void)
{
  g_wifi.configured_role = WIFI_ROLE_STA;
  assert(wifi_connect(NULL) == -ENETDOWN && !command_calls);
  g_wifi.admin_up = true;
  strcpy(g_wifi.sta_config.ssid, "test");
  assert(wifi_connect(NULL) == 0 && command_calls == 2 && !stop_calls);
  assert(g_wifi.role_state == WIFI_ROLE_STARTING);
  wifi_sta_event(true, 0);
  assert(g_wifi.role_state == WIFI_ROLE_ACTIVE && notified_carrier && g_wifi.tx_gate);
  wifi_sta_event(false, 1);
  assert(g_wifi.role_state == WIFI_ROLE_STARTING && !notified_carrier && !g_wifi.tx_gate);
  wifi_sta_event(true, 0); /* CP automatic reconnect */
  assert(g_wifi.role_state == WIFI_ROLE_ACTIVE && notified_carrier);
  wifi_sta_event(false, 1);
  assert(wifi_connect(NULL) == 0 && stop_calls == 1 && command_calls == 4);
  stop_result = -ETIMEDOUT;
  assert(wifi_connect(NULL) == -ETIMEDOUT && command_calls == 4);
  stop_result = 0; command_error = -EIO;
  assert(wifi_connect(NULL) == -EIO && g_wifi.active_role == WIFI_ROLE_NONE);
  command_error = 0;
  assert(wifi_connect(NULL) == 0);
  g_wifi.role_state = WIFI_ROLE_STOPPING;
  int saved = notifications;
  wifi_sta_event(true, 0);
  assert(g_wifi.role_state == WIFI_ROLE_STOPPING && notifications == saved);
  wifi_sta_event(false, 1);
  assert(g_wifi.active_role == WIFI_ROLE_NONE && g_wifi.role_state == WIFI_ROLE_IDLE);
  assert(g_wifi.role_sem == 1);
  g_wifi.active_role = WIFI_ROLE_SOFTAP;
  saved = stop_calls;
  assert(wifi_connect(NULL) == -EBUSY && saved == stop_calls);
  puts("PASS: STA autoreconnect command, carrier transitions, explicit restart, stop failure, command failure, late events, role isolation");
}
'''

if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1])
    driver = (root / "bk7258_wifi.c").read_text()
    types = driver[driver.index("enum wifi_role\n"):driver.index("struct wifi_pending_node")]
    connect = driver[driver.index("static int wifi_connect("):driver.index("static int wifi_disconnect(")]
    events = driver[driver.index("static void wifi_sta_event("):driver.index("static void wifi_ap_start_event(")]
    run(common + source(root / "hardware/bk7258_wifi_ipc.h")
        + source(root / "include/bk7258_wifi.h") + types + stubs + events + connect + tests)
