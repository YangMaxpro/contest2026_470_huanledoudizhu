/* SPDX-License-Identifier: Apache-2.0 */
/* Native replacement of the vendor lwIP loopback poll stimulus. */
#include <errno.h>
#include <net/if.h>
#include <nuttx/net/net.h>
#include <nuttx/net/netdev.h>
#include "devif/devif.h"
#include "netdev/netdev.h"

int rtsa_loopback_ready(void)
{
  int result = -ENODEV;
  net_lock();
  struct net_driver_s *dev = netdev_findbyname("lo");
  if (dev && IFF_IS_UP(dev->d_flags) && dev->d_txavail) result = 0;
  net_unlock();
  return result;
}

void rtsa_bk_netif_trigger_loopnetif_msg(void)
{
  /* Match the vendor's deferred poll, not synchronous packet processing:
   * lo_txavail queues HPWORK and drains pending UDP work under net_lock.
   * The SDK retains responsibility for its wakeup counter on send failure. */
  net_lock();
  struct net_driver_s *dev = netdev_findbyname("lo");
  if (dev && IFF_IS_UP(dev->d_flags)) netdev_txnotify_dev(dev, UDP_POLL);
  net_unlock();
}
