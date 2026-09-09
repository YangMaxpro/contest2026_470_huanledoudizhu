#!/usr/bin/env python3
"""Exercise the actual TLS entropy callback, including CP-style short reads."""
import pathlib
import sys
from test_cp_random import common, run

stubs = r'''
#define O_RDONLY 0
#define XIAOPAI_RANDOM_DEVICE "/dev/random"
#define MBEDTLS_ERR_ENTROPY_SOURCE_FAILED -0x003c
struct xiaopai_tls { bool expired; };
static int mode, reads, closes, opens;
static bool tls_expired(struct xiaopai_tls *t) { return t->expired; }
static int fake_open(const char *path, int flags)
{ assert(!strcmp(path,"/dev/random") && flags == O_RDONLY); opens++; return mode == 4 ? -1 : 5; }
static ssize_t fake_read(int fd, void *p, size_t n)
{
  assert(fd == 5); reads++;
  if (mode == 1 && reads == 1) { errno = EINTR; return -1; }
  if (mode == 2 && reads == 2) return 0;
  if (mode == 3 && reads == 2) { errno = EIO; return -1; }
  if (n > 7) n = 7;
  memset(p, 0x5a, n); return n;
}
static int fake_close(int fd) { assert(fd == 5); closes++; return 0; }
#define open fake_open
#define read fake_read
#define close fake_close
'''
tests = r'''
int main(void)
{
  struct xiaopai_tls tls = {0};
  unsigned char out[50];
  for (mode = 0; mode < 5; mode++)
    {
      opens = reads = closes = 0;
      memset(out, 0xa5, sizeof(out));
      int ret = tls_entropy(&tls, out + 1, 48);
      assert(opens == 1 && out[0] == 0xa5 && out[49] == 0xa5);
      assert(closes == (mode == 4 ? 0 : 1));
      assert(ret == (mode < 2 ? 0 : MBEDTLS_ERR_ENTROPY_SOURCE_FAILED));
      for (int i = 1; i < 49; i++) assert(out[i] == (mode < 2 ? 0x5a : 0));
    }
  mode = 0; reads = closes = 0; tls.expired = true;
  assert(tls_entropy(&tls, out, sizeof(out)) == MBEDTLS_ERR_ENTROPY_SOURCE_FAILED);
  assert(reads == 0 && closes == 1);
  for (unsigned i = 0; i < sizeof(out); i++) assert(out[i] == 0);
  puts("PASS: TLS entropy short reads, EINTR, EOF, errors, deadline, failure zeroization and close");
}
'''
text = pathlib.Path(sys.argv[1]).read_text()
callback = text[text.index("static int tls_entropy("):text.index("static int tls_send_raw(")]
run(common + stubs + callback + tests)
