#!/usr/bin/env python3
"""No cloud calls: validate newlib ctype flags and IPv4 text conversion."""
import pathlib
import signal
import subprocess
import sys
import tempfile

source = pathlib.Path(sys.argv[1]).resolve()
test = r'''
#include <assert.h>
#include <ctype.h>
#include <locale.h>
#include <sys/resource.h>
#include "rtsa_libc.c"
int main(int argc, char **argv)
{
  (void)argv;
  struct rlimit limit = {0, 0};
  assert(setrlimit(RLIMIT_CORE, &limit) == 0);
  if (argc == 2) rtsa_abort();
  if (argc == 3) rtsa___assert_func("private-file", 123, "private-function", "private-expression");
  assert(setlocale(LC_CTYPE, "C"));
  assert(rtsa__ctype_[0] == 0);
  for (int i = 0; i < 256; i++)
    {
      unsigned char f = rtsa__ctype_[i + 1];
      assert(!!(f & 1) == !!isupper(i));
      assert(!!(f & 2) == !!islower(i));
      assert(!!(f & 4) == !!isdigit(i));
      assert(!!(f & 8) == !!isspace(i));
      assert(!!(f & 16) == !!ispunct(i));
      assert(!!(f & 32) == !!iscntrl(i));
      assert(!!(f & (64|4)) == !!isxdigit(i));
      assert(!!(f & (1|2|4|16|128)) == !!isprint(i));
    }
  assert(rtsa_ipaddr_addr("127.0.0.1") == htonl(0x7f000001));
  assert(rtsa_ipaddr_addr("0.0.0.0") == 0);
  assert(rtsa_ipaddr_addr("255.255.255.255") == INADDR_NONE);
  assert(rtsa_ipaddr_addr("invalid") == INADDR_NONE);
  assert(rtsa_ipaddr_addr(NULL) == INADDR_NONE);
}
'''
with tempfile.TemporaryDirectory(prefix="rtsa-libc-") as tmp:
    src = pathlib.Path(tmp) / "test.c"
    exe = pathlib.Path(tmp) / "test"
    src.write_text(test)
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-I" + str(source.parent), str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=15)
    for args, expected in [(["abort"], "RTSA fatal: abort caller="),
                           (["assert", "test"], "RTSA fatal: assertion caller=")]:
        result = subprocess.run([str(exe), *args], capture_output=True, text=True, timeout=15)
        assert result.returncode == -signal.SIGABRT, result
        assert expected in result.stdout, result
        assert "private-" not in result.stdout, result
print("PASS RTSA libc: ctype, IPv4 conversion, fatal diagnostics preserve SIGABRT without private strings")
