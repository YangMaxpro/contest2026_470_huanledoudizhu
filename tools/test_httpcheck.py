#!/usr/bin/env python3
"""Test the real XiaoPai wrapper and NuttX HTTP parser on Linux loopback.

Usage: test_httpcheck.py /path/to/apps /path/to/app/xiaopai
No external network or hardware is used.
"""
import pathlib
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time

apps, app = map(pathlib.Path, sys.argv[1:3])

CONFIG = '''
#define FAR
#define CODE
#define OK 0
#define ERROR (-1)
#define UNUSED(x) ((void)(x))
#define CONFIG_NET_IPv4 1
#define CONFIG_LIBC_NETDB 1
#define CONFIG_DEBUG_ASSERTIONS 1
#define CONFIG_WEBCLIENT_TIMEOUT 2
#include <stddef.h>
size_t strlcpy(char *, const char *, size_t);
'''
NETLIB = '''
#include <nuttx/config.h>
#include <stdint.h>
struct url_s {
 char *scheme; int schemelen; char *host; int hostlen;
 uint16_t port; char *path; int pathlen;
};
int netlib_parseurl(const char *, struct url_s *);
'''
MAIN = '''
#include <stdio.h>
#include <string.h>
#include <dirent.h>
#include "xiaopai_httpcheck.h"
size_t strlcpy(char *dst, const char *src, size_t n) {
 size_t len = strlen(src);
 if (n) { size_t copy = len < n - 1 ? len : n - 1;
 memcpy(dst, src, copy); dst[copy] = 0; } return len;
}
static int fdcount(void) {
 DIR *d = opendir("/proc/self/fd"); int n = 0;
 while (readdir(d)) n++; closedir(d); return n;
}
int main(int argc, char **argv) {
 int before = fdcount();
 int ret = xiaopai_httpcheck(argc > 1 ? argv[1] : NULL);
 if (fdcount() != before) { puts("FD_LEAK"); return 99; }
 return ret == 0 ? 0 : 1;
}
'''


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.request.recv(2048)
            if not chunk:
                return
            data += chunk
        path = data.split(b" ")[1].decode()
        self.server.paths.append(path)
        cases = {
            "/ok": b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello",
            "/chunked": (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
                         b"2\r\nhe\r\n3\r\nllo\r\n0\r\n\r\n"),
            "/empty": b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n",
            "/missing": b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n",
            "/redirect": (b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:"
                          + str(self.server.server_address[1]).encode()
                          + b"/unexpected\r\nContent-Length: 0\r\n\r\n"),
            "/truncated": b"HTTP/1.1 200 OK\r\nContent-Length: 99\r\n\r\nshort",
            "/large": b"HTTP/1.1 200 OK\r\nContent-Length: 40000\r\n\r\n" + b"x" * 40000,
            "/bad": b"NOT-HTTP\r\n\r\n",
            "/longheader": b"HTTP/1.1 200 OK\r\nX-Long: " + b"x" * 512 + b"\r\n\r\n",
        }
        try:
            if path == "/stall":
                time.sleep(2)
                return
            response = cases[path]
            if path == "/chunked":
                for start in range(0, len(response), 3):
                    self.request.sendall(response[start:start + 3])
                    time.sleep(0.002)
            else:
                self.request.sendall(response)
        except (BrokenPipeError, ConnectionResetError):
            pass


with tempfile.TemporaryDirectory() as directory:
    root = pathlib.Path(directory)
    (root / "nuttx").mkdir()
    (root / "netutils").mkdir()
    (root / "nuttx/config.h").write_text(CONFIG)
    (root / "nuttx/compiler.h").write_text("#include <nuttx/config.h>\n")
    (root / "nuttx/version.h").write_text(
        '#define CONFIG_VERSION_MAJOR 0\n#define CONFIG_VERSION_MINOR 0\n')
    (root / "debug.h").write_text(
        '#include <assert.h>\n#define DEBUGASSERT assert\n'
        '#define nerr(...) ((void)0)\n#define ninfo(...) ((void)0)\n'
        '#define nwarn(...) ((void)0)\n')
    (root / "netutils/netlib.h").write_text(NETLIB)
    shutil.copy(apps / "include/netutils/webclient.h", root / "netutils")
    (root / "main.c").write_text(MAIN)
    binary = root / "httpcheck"
    subprocess.run([
        "cc", "-std=gnu11", "-g", "-DXIAOPAI_HTTP_TIMEOUT_MS=1000",
        "-I", str(root), "-I", str(app), str(root / "main.c"),
        str(app / "xiaopai_httpcheck.c"),
        str(apps / "netutils/webclient/webclient.c"),
        str(apps / "netutils/netlib/netlib_parseurl.c"), "-o", str(binary)
    ], check=True)

    def run(url, success, expected=None):
        result = subprocess.run([str(binary), url], capture_output=True,
                                text=True, timeout=5)
        assert result.returncode == (0 if success else 1), result.stdout + result.stderr
        assert "FD_LEAK" not in result.stdout, result.stdout
        if expected:
            assert expected in result.stdout, result.stdout

    with Server(("127.0.0.1", 0), Handler) as server:
        server.paths = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            run(base + "/ok", True, "body_bytes=5")
            run(base + "/chunked", True, "body_bytes=5")
            run(base + "/empty", True, "status=204")
            for path in ("missing", "redirect", "truncated", "large", "bad", "longheader", "stall"):
                run(base + "/" + path, False)
            for url in ("https://example.com/", "http://user:pass@localhost/", "http://localhost/\r\nX: y"):
                run(url, False)
            assert "/unexpected" not in server.paths
        finally:
            server.shutdown()
            thread.join()
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
    run(f"http://127.0.0.1:{port}/", False)
print("PASS: 14 HTTP cases, real parser, fragmented chunked body, deadline, "
      "redirect blocked, body limit, errors, descriptor cleanup")
