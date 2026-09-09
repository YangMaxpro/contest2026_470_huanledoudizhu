/* SPDX-License-Identifier: Apache-2.0 */
#include <nuttx/config.h>
#include <arch/chip/bk7258_wifi_profile.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <sched.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>
#include <netutils/netlib.h>
#include <wireless/wapi.h>
#include "xiaopai_netwatch.h"
#include "xiaopai_wifi.h"

static pthread_mutex_t g_wifi_lock = PTHREAD_MUTEX_INITIALIZER;
static bool g_boot_pending = true;

static int wifi_password(struct bk7258_wifi_profile *p)
{
  struct timespec started;
  bool overflow = false;
  size_t used = 0;
  int ret = 0;
  int fd = open("/dev/console", O_RDWR | O_NONBLOCK);
#ifdef CONFIG_SERIAL_TERMIOS
  struct termios saved;
  struct termios hidden;
#endif
  if (fd < 0) return -errno;
#ifdef CONFIG_SERIAL_TERMIOS
  if (tcgetattr(fd, &saved) < 0)
    { ret = -errno; goto close_input; }
  hidden = saved;
  hidden.c_lflag &= ~(ECHO | ECHONL | ICANON | ISIG);
  hidden.c_cc[VMIN] = 1;
  hidden.c_cc[VTIME] = 0;
  if (tcsetattr(fd, TCSANOW, &hidden) < 0)
    { ret = -errno; goto close_input; }
#endif
  printf("Wi-Fi password (hidden; turn local echo OFF; Ctrl-C cancels): ");
  fflush(stdout);
  clock_gettime(CLOCK_MONOTONIC, &started);
  for (;;)
    {
      struct timespec now;
      struct pollfd input = { .fd = fd, .events = POLLIN };
      unsigned char c;
      ssize_t n;
      clock_gettime(CLOCK_MONOTONIC, &now);
      if (now.tv_sec - started.tv_sec >= 120)
        { ret = -ETIMEDOUT; break; }
      ret = poll(&input, 1, 1000);
      if (ret < 0)
        {
          if (errno == EINTR) continue;
          ret = -errno;
          break;
        }
      if (ret == 0) continue;
      if (input.revents & (POLLERR | POLLHUP | POLLNVAL))
        { ret = -EIO; break; }
      n = read(fd, &c, 1);
      if (n < 0 && (errno == EINTR || errno == EAGAIN)) continue;
      if (n <= 0) { ret = n == 0 ? -EIO : -errno; break; }
      ret = 0;
      if (c == 3 || c == 4) { ret = -ECANCELED; break; }
      if (c == '\r' || c == '\n')
        {
          if (used == 0 && !overflow) continue; /* Trailing NSH CR/LF. */
          break;
        }
      if (c == '\b' || c == 127)
        { if (used) p->password[--used] = 0; continue; }
      if (used == sizeof(p->password) || c < 32 || c > 126)
        overflow = true;
      else
        p->password[used++] = c;
    }
#ifdef CONFIG_SERIAL_TERMIOS
  if (tcsetattr(fd, TCSANOW, &saved) < 0) ret = -errno;
close_input:
#endif
  close(fd);
  printf("\n");
  p->password_length = used;
  if (ret == 0 && (overflow || !bk7258_wifi_profile_valid(p))) ret = -EINVAL;
  return ret;
}

static int wifi_join(const struct bk7258_wifi_profile *p)
{
  char ssid[33] = {0};
  int fd;
  int ret;
  /* ensure is idempotent, but refuses a monitor whose stop is still pending. */
  ret = xiaopai_netwatch_ensure();
  if (ret < 0) return ret;
  fd = wapi_make_socket();
  if (fd < 0) return -errno;
  memcpy(ssid, p->ssid, p->ssid_length);
  ret = netlib_ifup(CONFIG_BK7258_WIFI_IFNAME);
  if (ret < 0) ret = -errno;
  if (ret == 0)
    ret = wapi_set_mode(fd, CONFIG_BK7258_WIFI_IFNAME, WAPI_MODE_MANAGED);
  if (ret == 0)
    ret = wpa_driver_wext_set_key_ext(fd, CONFIG_BK7258_WIFI_IFNAME,
                                     WPA_ALG_CCMP, (const char *)p->password,
                                     p->password_length);
  if (ret == 0)
    ret = wapi_set_essid(fd, CONFIG_BK7258_WIFI_IFNAME, ssid, WAPI_ESSID_ON);
  close(fd);
  if (ret == 0)
    printf("wifi v33: connection requested; netwatch owns DHCP\n");
  return ret;
}

static int wifi_boot_worker(int argc, char **argv)
{
  struct bk7258_wifi_profile p = {0};
  int ret = -ENOENT;
  unsigned int attempt;
  (void)argc;
  (void)argv;
  pthread_mutex_lock(&g_wifi_lock);
  if (!g_boot_pending) goto done;
  g_boot_pending = false;
  for (attempt = 0; attempt < 3; attempt++)
    {
      ret = bk7258_wifi_profile_command(BK7258_WIFI_PROFILE_GET, &p);
      if (ret == 0 || ret == -ENOENT || ret == -EINVAL || ret == -EPROTO)
        break;
      if (attempt < 2) sleep(2);
    }
  if (ret == 0) ret = wifi_join(&p);
  if (ret == -ENOENT)
    printf("wifi v33: no saved profile; use xiaopai wifi save <SSID>\n");
  else if (ret < 0)
    printf("wifi v33: boot connect error=%d; use xiaopai wifi connect\n", -ret);
done:
  explicit_bzero(&p, sizeof(p));
  pthread_mutex_unlock(&g_wifi_lock);
  return 0;
}

/* Keep application startup out of the board/driver ownership boundary. The
 * boot NSH still runs on CONFIG_INIT_STACKSIZE, which must remain 4096+. */
extern int nsh_main(int argc, char **argv);
int xiaopai_boot_main(int argc, char **argv)
{
  if (task_create("xiaopai_wifi_boot", 100, 4096, wifi_boot_worker, NULL) < 0)
    printf("wifi v33: boot worker failed=%d; console remains available\n", errno);
  return nsh_main(argc, argv);
}

int xiaopai_wifi(int argc, char **argv)
{
  struct bk7258_wifi_profile p = {0};
  int ret;
  if (argc < 1 ||
      !((argc == 2 && strcmp(argv[0], "save") == 0) ||
        (argc == 1 && (strcmp(argv[0], "connect") == 0 ||
                       strcmp(argv[0], "status") == 0 ||
                       strcmp(argv[0], "forget") == 0))))
    {
      printf("Usage: xiaopai wifi save <SSID>|connect|status|forget\n");
      return -EINVAL;
    }
  ret = pthread_mutex_trylock(&g_wifi_lock);
  if (ret != 0)
    { printf("wifi: configuration busy; retry shortly\n"); return -ret; }
  if (strcmp(argv[0], "status") != 0) g_boot_pending = false;
  if (strcmp(argv[0], "forget") == 0)
    {
      ret = bk7258_wifi_profile_command(BK7258_WIFI_PROFILE_CLEAR, NULL);
      if (ret == 0)
        printf("wifi: saved profile removed; current RAM connection unchanged\n");
    }
  else if (strcmp(argv[0], "save") == 0)
    {
      size_t n = strlen(argv[1]);
      ret = -EINVAL;
      if (n == 0 || n > sizeof(p.ssid)) goto done;
      p.version = BK7258_WIFI_PROFILE_VERSION;
      p.ssid_length = n;
      memcpy(p.ssid, argv[1], n);
      printf("wifi: saves plaintext Wi-Fi credentials to board Flash; "
             "8..63 ASCII password\n");
      ret = wifi_password(&p);
      if (ret != 0) goto done;
      ret = bk7258_wifi_profile_command(BK7258_WIFI_PROFILE_SET, &p);
      if (ret != 0) goto done;
      printf("wifi: profile saved and read back; boot auto-connect enabled\n");
      ret = wifi_join(&p);
    }
  else
    {
      ret = bk7258_wifi_profile_command(BK7258_WIFI_PROFILE_GET, &p);
      if (strcmp(argv[0], "status") == 0)
        {
          printf("wifi v33: saved=%s; credentials are not printed\n",
                 ret == 0 ? "yes" : ret == -ENOENT ? "no" : "unreadable");
          if (ret == -ENOENT) ret = 0;
        }
      else if (ret == 0) ret = wifi_join(&p);
    }
done:
  if (ret < 0) printf("wifi: operation failed error=%d\n", -ret);
  explicit_bzero(&p, sizeof(p));
  pthread_mutex_unlock(&g_wifi_lock);
  return ret;
}
