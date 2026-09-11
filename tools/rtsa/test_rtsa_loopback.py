#!/usr/bin/env python3
"""Exercise loopback callback/locking with a native-network boundary mock."""
import pathlib
import subprocess
import sys
import tempfile

source = pathlib.Path(sys.argv[1]).resolve()
header = r'''
#ifndef MOCK_NET
#define MOCK_NET
#include <stdint.h>
struct net_driver_s { unsigned int d_flags; int (*d_txavail)(struct net_driver_s *); };
void net_lock(void);
void net_unlock(void);
struct net_driver_s *netdev_findbyname(const char *name);
void netdev_txnotify_dev(struct net_driver_s *dev, uint32_t flags);
#define UDP_POLL (1 << 5)
#define IFF_IS_UP(flags) ((flags) & 1)
#endif
'''
test = r'''
#include <assert.h>
#include <string.h>
#include "rtsa_loopback.c"
static int locked, present, notifications;
static int txavail(struct net_driver_s *dev) { (void)dev; return 0; }
static struct net_driver_s device;
void net_lock(void) { assert(!locked); locked = 1; }
void net_unlock(void) { assert(locked); locked = 0; }
struct net_driver_s *netdev_findbyname(const char *name)
{ assert(locked && !strcmp(name, "lo")); return present ? &device : NULL; }
void netdev_txnotify_dev(struct net_driver_s *dev, uint32_t flags)
{ assert(locked && dev == &device && flags == UDP_POLL); notifications++; }
int main(void)
{
  assert(rtsa_loopback_ready() == -ENODEV);
  rtsa_bk_netif_trigger_loopnetif_msg(); assert(!locked && !notifications);
  present = 1;
  assert(rtsa_loopback_ready() == -ENODEV);
  rtsa_bk_netif_trigger_loopnetif_msg(); assert(!notifications);
  device.d_flags = 1;
  assert(rtsa_loopback_ready() == -ENODEV);
  device.d_txavail = txavail;
  assert(rtsa_loopback_ready() == 0);
  rtsa_bk_netif_trigger_loopnetif_msg();
  assert(!locked && notifications == 1);
}
'''
with tempfile.TemporaryDirectory(prefix="rtsa-loopback-") as tmp:
    root = pathlib.Path(tmp)
    for name in ("net/if.h", "nuttx/net/net.h", "nuttx/net/netdev.h", "devif/devif.h", "netdev/netdev.h"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(header)
    src, exe = root / "test.c", root / "test"
    src.write_text(test)
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-I"+str(root), "-I"+str(source.parent), str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=15)
print("PASS RTSA loopback: missing/down device rejection and locked UDP poll notification")
