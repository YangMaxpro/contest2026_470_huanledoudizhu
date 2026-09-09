#!/usr/bin/env python3
"""Compile production profile code with deterministic storage/console stubs."""
import pathlib
import sys
from test_cp_random import common, run, source

root = pathlib.Path(sys.argv[1])
abi = source(root / "nuttx/arch/arm/src/bk7258/include/bk7258_wifi_profile.h")
app = root / "contest2026_470_huanledoudizhu/app/xiaopai"
service = source(root / "contest2026_470_huanledoudizhu/tools/cp-v33/xiaopai_wifi_profile_service.h")

storage = r'''
#define EF_NO_ERR 0
static unsigned char flash_blob[128];
static size_t flash_size;
static int write_error, silent_error, writes;
static size_t ef_get_env_blob(const char *key, void *out, size_t n, size_t *len)
{
  assert(!strcmp(key, "xiaopai.wifi.v1"));
  *len = flash_size;
  if (n > flash_size) n = flash_size;
  memcpy(out, flash_blob, n);
  return n;
}
static int ef_set_env_blob(const char *key, const void *in, size_t n)
{
  assert(!strcmp(key, "xiaopai.wifi.v1"));
  writes++;
  if (write_error) return -1;
  if (!silent_error)
    {
      flash_size = n;
      if (n) memcpy(flash_blob, in, n);
    }
  return 0;
}
'''
cp_tests = r'''
int main(void)
{
  struct bk7258_wifi_profile_request q = {0};
  struct bk7258_wifi_profile_response r;
  struct bk7258_wifi_profile zero = {0};
  xiaopai_profile_service(&q, sizeof(q)-1, &r);
  assert(r.status == BK7258_WIFI_PROFILE_INVALID && !writes);
  xiaopai_profile_service(&q, sizeof(q), &r);
  assert(r.status == BK7258_WIFI_PROFILE_MISSING);
  q.operation = BK7258_WIFI_PROFILE_CLEAR;
  xiaopai_profile_service(&q, sizeof(q), &r);
  assert(!r.status && !writes);
  q.operation = BK7258_WIFI_PROFILE_SET;
  q.profile.version = 1; q.profile.ssid_length = 4;
  memcpy(q.profile.ssid, "test", 4);
  q.profile.password_length = 8; memcpy(q.profile.password, "testpass", 8);
  assert(bk7258_wifi_profile_valid(&q.profile));
  q.profile.reserved = 1;
  xiaopai_profile_service(&q, sizeof(q), &r);
  assert(r.status == BK7258_WIFI_PROFILE_INVALID && !writes);
  q.profile.reserved = 0;
  write_error = 1;
  xiaopai_profile_service(&q, sizeof(q), &r);
  assert(r.status == BK7258_WIFI_PROFILE_IO);
  write_error = 0; silent_error = 1;
  xiaopai_profile_service(&q, sizeof(q), &r);
  assert(r.status == BK7258_WIFI_PROFILE_IO);
  silent_error = 0;
  xiaopai_profile_service(&q, sizeof(q), &r);
  assert(!r.status && !memcmp(&r.profile, &zero, sizeof(zero)));
  int n = writes;
  xiaopai_profile_service(&q, sizeof(q), &r);
  assert(!r.status && writes == n);
  q.operation = BK7258_WIFI_PROFILE_GET;
  q.profile = zero;
  xiaopai_profile_service(&q, sizeof(q), &r);
  assert(!r.status && r.profile.password_length == 8);
  flash_size++;
  xiaopai_profile_service(&q, sizeof(q), &r);
  assert(r.status == BK7258_WIFI_PROFILE_INVALID &&
         !memcmp(&r.profile, &zero, sizeof(zero)));
  flash_size--; flash_blob[0] = 99;
  xiaopai_profile_service(&q, sizeof(q), &r);
  assert(r.status == BK7258_WIFI_PROFILE_INVALID);
  q.operation = BK7258_WIFI_PROFILE_CLEAR;
  silent_error = 1;
  xiaopai_profile_service(&q, sizeof(q), &r);
  assert(r.status == BK7258_WIFI_PROFILE_IO);
  silent_error = 0;
  xiaopai_profile_service(&q, sizeof(q), &r);
  assert(!r.status && !flash_size);
  puts("PASS: profile ABI, missing, malformed, corruption, storage failure, readback, dedup, clear");
}
'''
run(common + abi + storage + service + cp_tests)

transport = r'''
static int transport_error, transport_calls;
static uint16_t reply_size = sizeof(struct bk7258_wifi_profile_response);
static struct bk7258_wifi_profile_response reply;
static int wifi_command(uint16_t cmd, const void *data, uint16_t length,
                         void *out, uint16_t capacity, uint16_t *received)
{
  const struct bk7258_wifi_profile_request *q = data;
  assert(cmd == 0x214 && length == sizeof(*q) && capacity == sizeof(reply));
  if (q->operation != BK7258_WIFI_PROFILE_SET)
    {
      struct bk7258_wifi_profile zero = {0};
      assert(!memcmp(&zero, &q->profile, sizeof(zero)));
    }
  transport_calls++;
  if (transport_error) return transport_error;
  memcpy(out, &reply, sizeof(reply)); *received = reply_size;
  return 0;
}
'''
transport_tests = r'''
int main(void)
{
  struct bk7258_wifi_profile p = {0};
  assert(bk7258_wifi_profile_command(99, &p) == -EINVAL);
  assert(bk7258_wifi_profile_command(0, NULL) == -EINVAL);
  assert(bk7258_wifi_profile_command(1, &p) == -EINVAL && !transport_calls);
  transport_error = -ETIMEDOUT;
  assert(bk7258_wifi_profile_command(0, &p) == -ETIMEDOUT);
  transport_error = 0; reply_size = 0;
  assert(bk7258_wifi_profile_command(0, &p) == -EPROTO);
  reply_size = sizeof(reply); reply.status = BK7258_WIFI_PROFILE_MISSING;
  assert(bk7258_wifi_profile_command(0, &p) == -ENOENT);
  reply.status = BK7258_WIFI_PROFILE_INVALID;
  assert(bk7258_wifi_profile_command(0, &p) == -EINVAL);
  reply.status = BK7258_WIFI_PROFILE_IO;
  assert(bk7258_wifi_profile_command(0, &p) == -EIO);
  reply.status = 0;
  assert(bk7258_wifi_profile_command(0, &p) == -EPROTO);
  reply.profile.version = 1; reply.profile.ssid_length = 4;
  memcpy(reply.profile.ssid, "test", 4);
  reply.profile.password_length = 8; memcpy(reply.profile.password,"testpass",8);
  assert(bk7258_wifi_profile_command(0, &p) == 0 && p.password_length == 8);
  assert(bk7258_wifi_profile_command(1, &p) == 0);
  assert(bk7258_wifi_profile_command(2, NULL) == 0);
  puts("PASS: AP profile transport validation, old CP/short reply, timeout, status mapping");
}
'''
driver = (root / "nuttx/arch/arm/src/bk7258/bk7258_wifi.c").read_text()
profile_fn = driver[driver.index("int bk7258_wifi_profile_command("):
                    driver.index("int bk7258_wifi_random_block(")]
run(common + abi + transport + profile_fn + transport_tests)

stubs = r'''
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <time.h>
#include <stdarg.h>
#include <termios.h>
#define CONFIG_SERIAL_TERMIOS 1
#define CONFIG_BK7258_WIFI_IFNAME "xiaopai"
#define WAPI_MODE_MANAGED 1
#define WPA_ALG_CCMP 1
#define WAPI_ESSID_ON 1
static const char *input_text;
static unsigned input_pos, now;
static int requests, connection_calls, joins, ensure_error, join_error;
static int profile_error, profile_failures, task_error, calls_nsh, restore;
static unsigned last_op;
static struct bk7258_wifi_profile saved_profile;
static int bk_open(const char *name, int flags)
{ assert(!strcmp(name,"/dev/console") && (flags & O_NONBLOCK)); return 7; }
#define open bk_open
static int close(int fd) { assert(fd == 7 || fd == 8); return 0; }
static int fake_tcgetattr(int fd, struct termios *t)
{ assert(fd == 7); memset(t, 0, sizeof(*t)); t->c_lflag = ECHO; return 0; }
static int fake_tcsetattr(int fd, int action, const struct termios *t)
{ assert(fd == 7 && action == TCSANOW); if (t->c_lflag & ECHO) restore++; return 0; }
#define tcgetattr fake_tcgetattr
#define tcsetattr fake_tcsetattr
static int fake_poll(struct pollfd *p, nfds_t n, int ms)
{
  assert(n == 1 && ms == 1000); now++;
  if (!input_text || !input_text[input_pos]) return 0;
  p->revents = POLLIN; return 1;
}
#define poll fake_poll
static ssize_t read(int fd, void *p, size_t n)
{ assert(fd == 7 && n == 1); *(char *)p = input_text[input_pos++]; return 1; }
static int fake_clock_gettime(clockid_t id, struct timespec *t)
{ assert(id == CLOCK_MONOTONIC); t->tv_sec = now; t->tv_nsec = 0; return 0; }
#define clock_gettime fake_clock_gettime
static unsigned sleep(unsigned s) { now += s; return 0; }
static int wapi_make_socket(void) { return 8; }
static int netlib_ifup(const char *name)
{ assert(!strcmp(name, "xiaopai")); connection_calls++; return 0; }
static int wapi_set_mode(int fd, const char *name, int mode)
{ (void)name; assert(fd == 8 && mode == 1); connection_calls++; return 0; }
static int wpa_driver_wext_set_key_ext(int fd, const char *name, int alg,
                                     const char *key, size_t n)
{
  (void)name; assert(fd == 8 && alg == 1 && n == 8 && !memcmp(key,"testpass",8));
  connection_calls++; return 0;
}
static int wapi_set_essid(int fd, const char *name, const char *ssid, int state)
{
  (void)name; assert(fd == 8 && state == 1 && !strcmp(ssid,"test"));
  connection_calls++; joins++; return join_error;
}
static int xiaopai_netwatch_ensure(void) { return ensure_error; }
int bk7258_wifi_profile_command(unsigned op, struct bk7258_wifi_profile *p)
{
  requests++; last_op = op;
  if (profile_failures) { profile_failures--; return -ETIMEDOUT; }
  if (profile_error) return profile_error;
  if (op == BK7258_WIFI_PROFILE_GET) *p = saved_profile;
  if (op == BK7258_WIFI_PROFILE_SET) saved_profile = *p;
  return 0;
}
static int task_create(const char *name, int pri, int stack,
                       int (*entry)(int, char **), char **args)
{
  (void)name; (void)entry; (void)args; assert(pri == 100 && stack == 4096);
  if (task_error) { errno = ENOMEM; return -1; } return 42;
}
int nsh_main(int argc, char **argv) { (void)argc; (void)argv; calls_nsh++; return 0; }
'''
app_tests = r'''
static void reset(void)
{
  input_pos = now = requests = connection_calls = joins = 0;
  ensure_error = profile_error = profile_failures = task_error = 0;
  input_text = "\r\ntestpass\n";
  memset(&saved_profile, 0, sizeof(saved_profile));
  saved_profile.version = 1; saved_profile.ssid_length = 4;
  memcpy(saved_profile.ssid, "test", 4);
  saved_profile.password_length = 8;
  memcpy(saved_profile.password, "testpass", 8);
  g_boot_pending = true;
}
int main(void)
{
  char *save[] = {"save", "test"};
  char *connect[] = {"connect"};
  char *forget[] = {"forget"};
  reset(); profile_error = -ENOENT;
  wifi_boot_worker(0, NULL); assert(requests == 1 && !joins);
  reset(); profile_failures = 2;
  wifi_boot_worker(0, NULL); assert(requests == 3 && joins == 1 && now == 4);
  wifi_boot_worker(0, NULL); assert(requests == 3 && joins == 1);
  reset(); profile_failures = 5;
  wifi_boot_worker(0, NULL); assert(requests == 3 && !joins);
  reset(); task_error = 1;
  assert(xiaopai_boot_main(0, NULL) == 0 && calls_nsh == 1);
  reset(); ensure_error = -EBUSY;
  assert(xiaopai_wifi(1, connect) == -EBUSY && !connection_calls);
  reset();
  assert(xiaopai_wifi(2, save) == 0 && joins == 1 && restore == 1);
  assert(last_op == BK7258_WIFI_PROFILE_SET && requests == 1);
  wifi_boot_worker(0, NULL); assert(requests == 1);
  reset(); input_text = "\3";
  assert(xiaopai_wifi(2, save) == -ECANCELED && !requests && restore == 2);
  reset(); input_text = "short\n";
  assert(xiaopai_wifi(2, save) == -EINVAL && !requests);
  reset(); input_text = "";
  assert(xiaopai_wifi(2, save) == -ETIMEDOUT && !requests && now >= 120);
  reset(); input_text = "123456789012345678901234567890123456789012345678901234567890123456789\n";
  assert(xiaopai_wifi(2, save) == -EINVAL && !requests);
  reset(); profile_error = -EIO;
  assert(xiaopai_wifi(2, save) == -EIO && !joins);
  reset();
  assert(xiaopai_wifi(1, forget) == 0 && !connection_calls);
  assert(last_op == BK7258_WIFI_PROFILE_CLEAR);
  assert(pthread_mutex_lock(&g_wifi_lock) == 0);
  assert(xiaopai_wifi(1, connect) == -EBUSY);
  pthread_mutex_unlock(&g_wifi_lock);
  puts("PASS: boot retries/no profile, console survives failure, single DHCP owner, hidden input, cancel, timeout, invalid input, no join on save failure, serialization");
}
'''
run(common + abi + stubs + source(app / "xiaopai_wifi.c") + app_tests)
