/* SPDX-License-Identifier: Apache-2.0 */
#include <nuttx/config.h>
#include <nuttx/net/dns.h>
#include <arpa/inet.h>
#include <errno.h>
#include <inttypes.h>
#include <net/if.h>
#include <pthread.h>
#include <sched.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "netutils/dhcpc.h"
#include "netutils/netlib.h"
#include "netutils/ntpclient.h"
#include <arch/chip/bk7258_wifi.h>
#include "xiaopai_netwatch.h"

#define NETWATCH_IFNAME CONFIG_BK7258_WIFI_IFNAME

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static bool g_running;
static bool g_stop;
static unsigned int g_epoch;
static unsigned int g_attempts;
static unsigned int g_leases;
static int g_error;

static void netwatch_time_start(void)
{
  int ret;

  /* Resolve only after DHCP has installed the DNS server. ntpc_start() is
   * idempotent while its single daemon is running and restarts it if a prior
   * daemon exhausted its retries and stopped. */
  ret = ntpc_start();
  if (ret >= 0)
    {
      printf("netwatch: NTP sync active pid=%d\n", ret);
    }
  else
    {
      printf("netwatch: NTP sync start failed error=%d\n", -ret);
    }
}

static uint64_t netwatch_now(void)
{
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return now.tv_sec;
}

static bool netwatch_link(void)
{
  uint8_t flags = 0;
  return netlib_getifstatus(NETWATCH_IFNAME, &flags) == 0 &&
         (flags & (IFF_UP | IFF_RUNNING)) == (IFF_UP | IFF_RUNNING);
}

static void netwatch_event(enum bk7258_wifi_event_e event,
                          unsigned int value, void *arg)
{
  (void)value;
  (void)arg;
  if (event == BK7258_WIFI_EVENT_STA_DISCONNECTED)
    {
      /* Even a down/up between polls invalidates an in-flight DHCP result.
       * Never perform socket I/O in the Wi-Fi mailbox worker callback. */
      pthread_mutex_lock(&g_lock);
      g_epoch++;
      pthread_mutex_unlock(&g_lock);
    }
}

static int netwatch_clear(void)
{
  const struct in_addr zero = {0};
  int ret = 0;
  if (netlib_set_ipv4addr(NETWATCH_IFNAME, &zero) < 0)
    ret = -EIO;
  if (netlib_set_dripv4addr(NETWATCH_IFNAME, &zero) < 0)
    ret = -EIO;
  if (netlib_set_ipv4netmask(NETWATCH_IFNAME, &zero) < 0)
    ret = -EIO;
  /* This opt-in service owns IPv4/DNS for the single-interface board. */
  if (dns_default_nameserver() < 0)
    ret = -EIO;
  return ret;
}

static int netwatch_apply(const struct dhcpc_state *lease)
{
  if (lease->ipaddr.s_addr == 0 || lease->netmask.s_addr == 0 ||
      lease->lease_time == 0)
    return -EPROTO;
  if (netlib_set_ipv4netmask(NETWATCH_IFNAME, &lease->netmask) < 0 ||
      netlib_set_dripv4addr(NETWATCH_IFNAME, &lease->default_router) < 0 ||
      netlib_set_ipv4addr(NETWATCH_IFNAME, &lease->ipaddr) < 0 ||
      dns_default_nameserver() < 0)
    return -EIO;
  if (lease->dnsaddr.s_addr != 0 &&
      netlib_set_ipv4dnsaddr(&lease->dnsaddr) < 0)
    return -EIO;
  return 0;
}

static int netwatch_request(struct dhcpc_state *lease)
{
  uint8_t mac[IFHWADDRLEN];
  void *handle;
  int ret;
  if (netlib_getmacaddr(NETWATCH_IFNAME, mac) < 0)
    return -EIO;
  handle = dhcpc_open(NETWATCH_IFNAME, mac, sizeof(mac));
  if (handle == NULL)
    return errno != 0 ? -errno : -EIO;
  errno = 0;
  ret = dhcpc_request(handle, lease);
  ret = ret == 0 ? 0 : (errno != 0 ? -errno : -ETIMEDOUT);
  dhcpc_close(handle);
  return ret;
}

static bool netwatch_current(unsigned int epoch)
{
  bool current;
  pthread_mutex_lock(&g_lock);
  current = !g_stop && epoch == g_epoch;
  pthread_mutex_unlock(&g_lock);
  return current && netwatch_link();
}

static int netwatch_worker(int argc, char **argv)
{
  struct dhcpc_state lease;
  uint64_t due = 0;
  uint64_t expires = 0;
  unsigned int epoch;
  unsigned int seen_epoch = 0;
  unsigned int backoff = 5;
  bool previous_link = false;
  bool first = true;
  int ret;
  (void)argc;
  (void)argv;

  printf("netwatch v20: DHCP monitor started on %s\n", NETWATCH_IFNAME);
  for (;;)
    {
      bool link;
      bool stop;
      pthread_mutex_lock(&g_lock);
      epoch = g_epoch;
      stop = g_stop;
      pthread_mutex_unlock(&g_lock);
      if (stop)
        break;

      link = netwatch_link();
      if (!first && !link && !previous_link)
        seen_epoch = epoch; /* Repeated down events need no further clearing. */
      if (first || epoch != seen_epoch || link != previous_link ||
          (expires != 0 && netwatch_now() >= expires))
        {
          bool report = first || link != previous_link || expires != 0;
          ret = netwatch_clear();
          pthread_mutex_lock(&g_lock);
          g_error = ret;
          pthread_mutex_unlock(&g_lock);
          if (ret < 0)
            {
              sleep(1);
              continue;
            }
          if (report)
            printf("netwatch: link=%s; old IPv4 cleared\n", link ? "up" : "down");
          seen_epoch = epoch;
          previous_link = link;
          first = false;
          expires = 0;
          due = 0;
          backoff = 5;
        }

      if (!link || netwatch_now() < due)
        {
          sleep(1);
          continue;
        }

      pthread_mutex_lock(&g_lock);
      g_attempts++;
      pthread_mutex_unlock(&g_lock);
      memset(&lease, 0, sizeof(lease));
      ret = netwatch_request(&lease);
      if (!netwatch_current(epoch))
        {
          /* The library can set the address before returning. Discard and
           * clear it if the link changed or stop was requested meanwhile. */
          netwatch_clear();
          first = true;
          continue;
        }
      if (ret == 0)
        ret = netwatch_apply(&lease);
      if (!netwatch_current(epoch))
        {
          netwatch_clear();
          first = true;
          continue;
        }

      pthread_mutex_lock(&g_lock);
      g_error = ret;
      if (ret == 0)
        g_leases++;
      pthread_mutex_unlock(&g_lock);
      if (ret == 0)
        {
          char address[INET_ADDRSTRLEN];
          expires = netwatch_now() + lease.lease_time;
          due = netwatch_now() + (lease.lease_time > 1 ? lease.lease_time / 2 : 1);
          backoff = 5;
          inet_ntop(AF_INET, &lease.ipaddr, address, sizeof(address));
          printf("netwatch: DHCP ready ip=%s lease=%" PRIu32 "s\n",
                 address, lease.lease_time);
          netwatch_time_start();
        }
      else
        {
          /* Fail closed after a NAK, partial configuration or timeout. */
          netwatch_clear();
          expires = 0;
          due = netwatch_now() + backoff;
          printf("netwatch: DHCP error=%d; retry in %us\n", -ret, backoff);
          backoff = backoff < 30 ? (backoff < 15 ? backoff * 2 : 30) : 30;
        }
    }

  bk7258_wifi_unregister_event_callback(netwatch_event, NULL);
  ret = netwatch_clear();
  pthread_mutex_lock(&g_lock);
  g_error = ret;
  g_running = false;
  pthread_mutex_unlock(&g_lock);
  printf("netwatch: stopped; DHCP ownership released\n");
  return 0;
}

int xiaopai_netwatch(const char *action)
{
  int ret;
  pid_t pid;
  pthread_mutex_lock(&g_lock);
  if (strcmp(action, "status") == 0)
    {
      bool running = g_running;
      bool stopping = g_stop;
      unsigned int attempts = g_attempts;
      unsigned int leases = g_leases;
      int error = g_error;
      pthread_mutex_unlock(&g_lock);
      printf("netwatch v20: %s attempts=%u leases=%u last_error=%d\n",
             running ? (stopping ? "stopping" : "running") : "stopped",
             attempts, leases, error);
      return 0;
    }
  if (strcmp(action, "stop") == 0)
    {
      g_stop = true;
      pthread_mutex_unlock(&g_lock);
      printf("netwatch: stop requested; pending DHCP must finish first\n");
      return 0;
    }
  if (strcmp(action, "start") != 0 && strcmp(action, "ensure") != 0)
    {
      pthread_mutex_unlock(&g_lock);
      return -EINVAL;
    }
  if (g_running)
    {
      bool ready = strcmp(action, "ensure") == 0 && !g_stop;
      pthread_mutex_unlock(&g_lock);
      if (ready) return 0;
      printf("netwatch: already running or stopping\n");
      return -EBUSY;
    }
  g_running = true;
  g_stop = false;
  g_attempts = 0;
  g_leases = 0;
  g_error = 0;
  pthread_mutex_unlock(&g_lock);

  ret = bk7258_wifi_register_event_callback(netwatch_event, NULL);
  if (ret == 0)
    {
      pid = task_create("xiaopai_netwatch", 100, 4096, netwatch_worker, NULL);
      if (pid >= 0)
        return 0;
      ret = -errno;
      bk7258_wifi_unregister_event_callback(netwatch_event, NULL);
    }
  pthread_mutex_lock(&g_lock);
  g_error = ret;
  g_running = false;
  pthread_mutex_unlock(&g_lock);
  printf("netwatch: start failed %d\n", ret);
  return ret;
}

int xiaopai_netwatch_ensure(void)
{
  return xiaopai_netwatch("ensure");
}

int xiaopai_time_status(void)
{
  struct ntpc_status_s status;
  time_t now = time(NULL);
  memset(&status, 0, sizeof(status));
  if (ntpc_status(&status) < 0)
    {
      printf("time: NTP status unavailable unix=%ld\n", (long)now);
      return -EIO;
    }
  printf("time: unix=%ld ntp_samples=%u sync=%s\n", (long)now,
         status.nsamples, status.nsamples > 0 ? "received" : "pending");
  return 0;
}
