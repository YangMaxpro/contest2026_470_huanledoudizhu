#!/usr/bin/env python3
"""Run the actual netwatch worker against deterministic clock/link/DHCP stubs."""
import sys
from test_cp_random import common, run, source

stubs = r'''
#include <arpa/inet.h>
#include <inttypes.h>
#include <pthread.h>
#include <time.h>
#include <stdarg.h>
#include <sys/socket.h>
#define CONFIG_BK7258_WIFI_IFNAME "xiaopai"
#define CONFIG_NETUTILS_NTPCLIENT_NUM_SAMPLES 1
#define IFHWADDRLEN 6
#define IFF_UP 1
#define IFF_RUNNING 4
enum bk7258_wifi_event_e { BK7258_WIFI_EVENT_STA_DISCONNECTED = 1 };
struct dhcpc_state {
  struct in_addr serverid, ipaddr, netmask, dnsaddr, default_router;
  uint32_t lease_time;
};
struct ntpc_status_s {
  unsigned int nsamples;
  struct { int64_t offset, delay; const struct sockaddr *srv_addr;
           struct sockaddr_storage _srv_addr_store; } samples[1];
};
static unsigned now, scenario, requests, closes, resets, apply_dns, stop_at;
static int task_failure, registration_failure, registered;
static int ntp_starts, ntp_error;
static unsigned ntp_samples;
static unsigned opens;
static struct in_addr assigned;
static unsigned request_times[100];
static unsigned down_logs;
static int fake_printf(const char *format, ...)
{
  char buffer[512];
  va_list args;
  va_start(args, format);
  int ret = vsnprintf(buffer, sizeof(buffer), format, args);
  va_end(args);
  if (strstr(buffer, "netwatch: link=down;")) down_logs++;
  fputs(buffer, stdout);
  return ret;
}
#define printf fake_printf
static void netwatch_event(enum bk7258_wifi_event_e, unsigned, void *);
static void request_stop(void);
static int fake_clock_gettime(int id, struct timespec *t)
{ assert(id == CLOCK_MONOTONIC); t->tv_sec = now; t->tv_nsec = 0; return 0; }
#define clock_gettime fake_clock_gettime
static unsigned sleep(unsigned n)
{
  now += n;
  if (scenario == 0 && now >= 5 && now < 10)
    netwatch_event(BK7258_WIFI_EVENT_STA_DISCONNECTED, 0, NULL);
  if (now >= stop_at) request_stop();
  return 0;
}
static int netlib_getifstatus(const char *n, uint8_t *flags)
{
  assert(!strcmp(n, "xiaopai"));
  *flags = scenario == 0 && now >= 5 && now < 10 ? IFF_UP : IFF_UP | IFF_RUNNING;
  return 0;
}
static int netlib_set_ipv4addr(const char *n, const struct in_addr *a)
{ (void)n; assigned = *a; return 0; }
static int netlib_set_dripv4addr(const char *n, const struct in_addr *a)
{ (void)n; (void)a; return 0; }
static int netlib_set_ipv4netmask(const char *n, const struct in_addr *a)
{ (void)n; (void)a; return 0; }
static int dns_default_nameserver(void) { resets++; return 0; }
static int netlib_set_ipv4dnsaddr(const struct in_addr *a)
{ assert(a->s_addr != 0); apply_dns++; return 0; }
static int netlib_getmacaddr(const char *n, uint8_t *m)
{ (void)n; memset(m, 1, 6); return 0; }
static void *dhcpc_open(const char *n, const void *mac, int len)
{ (void)n; (void)mac; assert(len == 6); opens++; return &assigned; }
static void dhcpc_close(void *h) { assert(h == &assigned); closes++; }
static int ntpc_start(void)
{ ntp_starts++; if (!ntp_error) ntp_samples = 1; return ntp_error ? ntp_error : 43; }
static int ntpc_status(struct ntpc_status_s *s)
{ memset(s, 0, sizeof(*s)); s->nsamples = ntp_samples; return 0; }
static int dhcpc_request(void *h, struct dhcpc_state *lease)
{
  assert(h == &assigned && requests < 100);
  request_times[requests++] = now;
  if (scenario == 1) { errno = ETIMEDOUT; return -1; }
  lease->ipaddr.s_addr = htonl(0x0a000002);
  lease->netmask.s_addr = htonl(0xffffff00);
  lease->dnsaddr.s_addr = htonl(0x0a000001);
  lease->default_router.s_addr = lease->dnsaddr.s_addr;
  lease->lease_time = scenario == 4 ? 0 : 12;
  assigned = lease->ipaddr; /* Match the library's early address write. */
  if (scenario == 2 && requests == 1)
    netwatch_event(BK7258_WIFI_EVENT_STA_DISCONNECTED, 0, NULL);
  if (scenario == 3) request_stop();
  return 0;
}
static int bk7258_wifi_register_event_callback(
  void (*cb)(enum bk7258_wifi_event_e, unsigned, void *), void *arg)
{ (void)cb; (void)arg; if (registration_failure) return -EBUSY; registered++; return 0; }
static void bk7258_wifi_unregister_event_callback(
  void (*cb)(enum bk7258_wifi_event_e, unsigned, void *), void *arg)
{ (void)cb; (void)arg; assert(registered == 1); registered--; }
static int task_create(const char *n, int priority, int stack,
                       int (*entry)(int, char **), char **args)
{
  (void)n; (void)entry; (void)args; assert(priority == 100 && stack == 4096);
  if (task_failure) { errno = ENOMEM; return -1; }
  return 42;
}
'''
tests = r'''
static void request_stop(void) { g_stop = true; }
static void reset(unsigned mode, unsigned duration)
{
  now = requests = closes = resets = apply_dns = opens = ntp_starts = 0;
  ntp_samples = 0;
  down_logs = 0;
  scenario = mode; stop_at = duration;
  g_epoch = g_leases = g_attempts = 0;
  g_running = false; g_stop = false; g_error = 0;
  assigned.s_addr = 0;
  memset(request_times, 0, sizeof(request_times));
  assert(xiaopai_netwatch("start") == 0);
  assert(xiaopai_netwatch_ensure() == 0 && registered == 1);
  g_stop = true;
  assert(xiaopai_netwatch_ensure() == -EBUSY && registered == 1);
  g_stop = false;
  assert(xiaopai_netwatch("start") == -EBUSY);
}
int main(void)
{
  assert(xiaopai_netwatch("invalid") == -EINVAL);
  registration_failure = 1;
  assert(xiaopai_netwatch("start") == -EBUSY && !g_running);
  registration_failure = 0; task_failure = 1;
  assert(xiaopai_netwatch("start") == -ENOMEM && !g_running && !registered);
  task_failure = 0;

  reset(0, 24);
  netwatch_worker(0, NULL);
  assert(requests == 4 && g_leases == 4);
  assert(ntp_starts == 4 && xiaopai_time_status() == 0);
  assert(down_logs == 1);
  assert(request_times[0] == 0 && request_times[1] == 10);
  assert(request_times[2] == 16 && request_times[3] == 22);
  assert(!g_running && !registered && assigned.s_addr == 0 && opens == closes);

  reset(1, 70);
  netwatch_worker(0, NULL);
  assert(requests == 5 && g_leases == 0);
  unsigned expected[] = {0, 5, 15, 35, 65};
  for (unsigned i = 0; i < 5; i++) assert(request_times[i] == expected[i]);
  assert(assigned.s_addr == 0 && opens == closes);
  assert(ntp_starts == 0);

  reset(2, 1);
  netwatch_worker(0, NULL);
  assert(requests == 2 && g_leases == 1 && apply_dns == 1 && assigned.s_addr == 0);

  reset(3, 1);
  netwatch_worker(0, NULL);
  assert(requests == 1 && g_leases == 0 && apply_dns == 0 && assigned.s_addr == 0);

  reset(4, 6);
  netwatch_worker(0, NULL);
  assert(g_leases == 0 && apply_dns == 0 && assigned.s_addr == 0);
  assert(xiaopai_netwatch("status") == 0);
  assert(xiaopai_netwatch("stop") == 0);
  reset(0, 1); ntp_error = -ENOMEM;
  netwatch_worker(0, NULL);
  assert(ntp_starts == 1);
  ntp_error = 0;
  puts("PASS: netwatch reconnect, renewal, retry backoff, stale DHCP, stop, malformed lease, start failures, idempotent NTP start/restart, NTP failure");
}
'''

if __name__ == "__main__":
    run(common + stubs + source(sys.argv[1]) + tests)
