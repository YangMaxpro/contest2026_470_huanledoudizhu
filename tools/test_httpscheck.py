#!/usr/bin/env python3
"""Real Mbed TLS + HTTP parser tests against local, generated TLS fixtures.

Usage: test_httpscheck.py APPS XIAOPAI CONFIG
CONFIG is the generated NuttX .config. Requires cc, Python cryptography.
Only test binaries use the generated CA and the host /dev/urandom.
An optional --live also tests the production CA against the public default URL.
"""
import datetime
import json
import os
import pathlib
import shutil
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

apps, app, config = map(pathlib.Path, sys.argv[1:4])

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
#define CONFIG_XIAOPAI_HTTPSCHECK 1
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
#include <dirent.h>
#include <errno.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "xiaopai_httpcheck.h"
#ifdef TEST_MIMO
#define XIAOPAI_MIMO_URL getenv("TEST_MIMO_URL")
#include "xiaopai_mimo.c"
#endif
time_t time(time_t *out) {
 struct timespec ts; clock_gettime(CLOCK_REALTIME, &ts);
 time_t t = getenv("TEST_EPOCH_ZERO") ? 0 : ts.tv_sec;
 if (out) *out = t; return t;
}
size_t strlcpy(char *dst, const char *src, size_t n) {
 size_t len = strlen(src);
 if (n) { size_t copy = len < n - 1 ? len : n - 1;
 memcpy(dst, src, copy); dst[copy] = 0; } return len;
}
static int fdcount(void) {
 DIR *d = opendir("/proc/self/fd"); int n = 0;
 while (readdir(d)) n++; closedir(d); return n;
}
struct stream_state { size_t sent, received; bool cancel; int mode; };
static ssize_t source(void *arg,char *buffer,size_t capacity) {
 struct stream_state *s=arg;
 if(s->mode==2) return 0;
 if(s->mode==3) return capacity+1;
 size_t n=70001-s->sent; if(n>capacity)n=capacity; if(n>137)n=137;
 for(size_t i=0;i<n;i++)buffer[i]='a'+((s->sent+i)%26);
 s->sent+=n; return n;
}
static int sink(void *arg,const char *buffer,size_t length) {
 struct stream_state *s=arg;
 for(size_t i=0;i<length;i++)if(buffer[i]!='a'+((s->received+i)%26))return -EPROTO;
 s->received+=length;
 if(s->mode==1 && s->received>100)s->cancel=true;
 return 0;
}
static bool cancelled(void *arg) { return ((struct stream_state *)arg)->cancel; }
int main(int argc, char **argv) {
 int before = fdcount();
 int ret;
 if(getenv("TEST_STREAM_URL")) {
   struct stream_state state={0};
   struct xiaopai_http_post post={0};
   state.mode=atoi(getenv("TEST_STREAM_MODE"));
   post.source=source; post.body_length=70001; post.sink=sink;
   post.response_limit=state.mode==4?128:200000;
   post.cancelled=cancelled; post.arg=&state;
   ret=xiaopai_https_post(getenv("TEST_STREAM_URL"),&post);
   if(ret==0 && (state.sent!=70001 || state.received!=128000))return 98;
   printf("STREAM sent=%zu received=%zu error=%d\\n",state.sent,state.received,ret);
 } else
#ifdef TEST_MIMO
 if (getenv("TEST_MIMO_URL")) {
   strcpy(g_key,"sk-loopback-test-only");
   char *prompt[] = {"hello", "world"};
   ret = xiaopai_mimo_ask(2,prompt);
 } else
#endif
 ret = xiaopai_httpscheck(argc > 1 ? argv[1] : NULL);
 if (fdcount() != before) { puts("FD_LEAK"); return 99; }
 return ret == 0 ? 0 : 1;
}
'''


def make_cert(name, issuer_cert=None, issuer_key=None, expired=False, future=False):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.datetime.utcnow()
    start = now - datetime.timedelta(days=2)
    end = now + datetime.timedelta(days=2)
    if expired:
        end = now - datetime.timedelta(days=1)
    if future:
        start = now + datetime.timedelta(days=1)
    builder = (x509.CertificateBuilder().subject_name(subject)
               .issuer_name(issuer_cert.subject if issuer_cert else subject)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(start).not_valid_after(end)
               .add_extension(x509.BasicConstraints(ca=issuer_cert is None,
                                                   path_length=None), critical=True))
    if issuer_cert:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]),
                                        critical=False)
    return builder.sign(issuer_key or key, hashes.SHA256()), key


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        if self.server.stall:
            time.sleep(3)
            return
        self.request.settimeout(3)
        try:
            with self.server.context.wrap_socket(self.request, server_side=True) as sock:
                data = b""
                while b"\r\n\r\n" not in data:
                    part = sock.recv(2048)
                    if not part:
                        return
                    data += part
                self.server.hits += 1
                path = data.split(b" ")[1]
                if path.startswith(b"/stream"):
                    head, body = data.split(b"\r\n\r\n", 1)
                    headers = dict(line.split(b":", 1) for line in head.split(b"\r\n")[1:])
                    size = int(headers[b"Content-Length"].strip())
                    while len(body) < size:
                        part = sock.recv(2048)
                        if not part:
                            return
                        body += part
                    assert size == 70001 and body == bytes(97 + i % 26 for i in range(size))
                    if path == b"/stream401":
                        response = b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 6\r\n\r\nsecret"
                    else:
                        payload = bytes(97 + i % 26 for i in range(128000))
                        response = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
                        for offset in range(0, len(payload), 997):
                            part = payload[offset:offset+997]
                            response += f"{len(part):x}\r\n".encode() + part + b"\r\n"
                        response += b"0\r\n\r\n"
                elif path.startswith(b"/mimo"):
                    head, body = data.split(b"\r\n\r\n", 1)
                    headers = dict(line.split(b":", 1) for line in head.split(b"\r\n")[1:])
                    size = int(headers[b"Content-Length"].strip())
                    while len(body) < size:
                        chunk = sock.recv(2048)
                        if not chunk:
                            return
                        body += chunk
                    assert data.startswith(b"POST ")
                    assert headers[b"api-key"].strip() == b"sk-loopback-test-only"
                    request = json.loads(body[:size])
                    assert request["messages"][1]["content"] == "hello world"
                    assert request["thinking"] == {"type": "disabled"}
                    assert request["stream"] is False
                    assert request["max_completion_tokens"] == 256
                    self.server.posts += 1
                    status = 200
                    reply = {"choices": [{"finish_reason": "stop", "message": {"content": "Hello from fixture"}}]}
                    if path in (b"/mimo401", b"/mimo429", b"/mimo500"):
                        status = int(path[-3:])
                        reply = {"error": {"message": "sk-loopback-test-only"}}
                    if path == b"/mimolength":
                        reply["choices"][0]["finish_reason"] = "length"
                    payload = json.dumps(reply).encode()
                    if path == b"/mimooversize":
                        payload = b"x" * 9000
                    elif path == b"/mimojson":
                        payload = b"not-json"
                    elif path == b"/mimoreflect":
                        payload = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": "sk-loopback-test-only"}}]}).encode()
                    if path == b"/mimoredirect":
                        response = b"HTTP/1.1 302 Found\r\nLocation: https://localhost/leak\r\nContent-Length: 0\r\n\r\n"
                    elif path == b"/mimochunked":
                        response = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
                        for offset in range(0, len(payload), 13):
                            part = payload[offset:offset+13]
                            response += f"{len(part):x}\r\n".encode() + part + b"\r\n"
                        response += b"0\r\n\r\n"
                    else:
                        size = len(payload) + (10 if path == b"/mimotruncated" else 0)
                        response = f"HTTP/1.1 {status} Response\r\nContent-Length: {size}\r\n\r\n".encode() + payload
                elif path == b"/redirect":
                    response = b"HTTP/1.1 302 Found\r\nLocation: http://localhost/\r\nContent-Length: 0\r\n\r\n"
                elif path == b"/truncated":
                    response = b"HTTP/1.1 200 OK\r\nContent-Length: 99\r\n\r\nshort"
                elif path == b"/chunked":
                    response = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\nhe\r\n3\r\nllo\r\n0\r\n\r\n"
                else:
                    response = b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello"
                step = 1024 if path.startswith(b"/stream") else 7
                for offset in range(0, len(response), step):
                    sock.sendall(response[offset:offset + step])
                    if path == b"/chunked":
                        time.sleep(0.005)
                if path != b"/unclean":
                    sock.unwrap()  # Send authenticated TLS close_notify.
        except (ssl.SSLError, OSError):
            pass


with tempfile.TemporaryDirectory(prefix="xiaopai-https-") as tmp:
    root = pathlib.Path(tmp)
    inc = root / "include"
    (inc / "nuttx").mkdir(parents=True)
    (inc / "netutils").mkdir()
    mbed_config = []
    for line in config.read_text().splitlines():
        if line.startswith("CONFIG_MBEDTLS_") or line.startswith("CONFIG_PSA_"):
            name, value = line.split("=", 1)
            mbed_config.append(f"#define {name} {'1' if value == 'y' else value}\n")
    (inc / "nuttx/config.h").write_text(CONFIG + "".join(mbed_config))
    (inc / "nuttx/compiler.h").write_text("#include <nuttx/config.h>\n")
    (inc / "nuttx/version.h").write_text("#define CONFIG_VERSION_MAJOR 0\n#define CONFIG_VERSION_MINOR 0\n")
    (inc / "debug.h").write_text("#include <assert.h>\n#define DEBUGASSERT assert\n#define ninfo(...)\n#define nerr(...)\n#define nwarn(...)\n")
    (inc / "netutils/netlib.h").write_text(NETLIB)
    shutil.copy(apps / "include/netutils/webclient.h", inc / "netutils/webclient.h")
    for name in ("xiaopai_httpcheck.c", "xiaopai_httpcheck.h", "xiaopai_tls.c", "xiaopai_tls.h"):
        shutil.copy(app / name, root / name)
    ca, ca_key = make_cert("Test CA")
    pem = ca.public_bytes(serialization.Encoding.PEM).decode()
    (root / "xiaopai_tls_ca.h").write_text("static const char g_xiaopai_tls_ca[] = " + json.dumps(pem) + ";\n")
    (root / "main.c").write_text(MAIN)
    mbed = apps / "crypto/mbedtls/mbedtls"
    binary = root / "https-test"
    command = ["cc", "-std=gnu11", "-O1", "-g", "-fsanitize=undefined",
               "-DXIAOPAI_HTTPS_TIMEOUT_MS=2000", '-DXIAOPAI_RANDOM_DEVICE="/dev/urandom"',
               "-I" + str(inc), "-I" + str(apps / "crypto/mbedtls/include"),
               "-I" + str(mbed / "include"), "-I" + str(root),
               str(root / "main.c"), str(root / "xiaopai_httpcheck.c"),
               str(root / "xiaopai_tls.c"),
               str(apps / "netutils/webclient/webclient.c"),
               str(apps / "netutils/netlib/netlib_parseurl.c")]
    command += [str(p) for p in sorted((mbed / "library").glob("*.c"))]
    command += ["-o", str(binary), "-pthread"]
    if "--mimo" in sys.argv[4:]:
        for name in ("xiaopai_mimo.c", "xiaopai_mimo.h"):
            shutil.copy(app / name, root / name)
        shutil.copy(apps / "netutils/cjson/cJSON/cJSON.h", inc / "netutils/cJSON.h")
        command += ["-DTEST_MIMO", str(apps / "netutils/cjson/cJSON/cJSON.c"), "-lm"]
    subprocess.run(command, check=True)
    cases = [("valid", "localhost", False, False, False, "/ok", True),
             ("chunked", "localhost", False, False, False, "/chunked", True),
             ("wrong-host", "other.local", False, False, False, "/ok", False),
             ("expired", "localhost", True, False, False, "/ok", False),
             ("future", "localhost", False, True, False, "/ok", False),
             ("untrusted", "localhost", False, False, True, "/ok", False),
             ("redirect", "localhost", False, False, False, "/redirect", False),
             ("truncated", "localhost", False, False, False, "/truncated", False),
             ("unclean", "localhost", False, False, False, "/unclean", False),
             ("stall", "localhost", False, False, False, "/ok", False),
             ("epoch-zero", "localhost", False, False, False, "/ok", False)]
    for label, hostname, expired, future, untrusted, path, success in cases:
        issuer, issuer_key = make_cert("Other CA") if untrusted else (ca, ca_key)
        cert, key = make_cert(hostname, issuer, issuer_key, expired, future)
        cert_path, key_path = root / "server.pem", root / "server.key"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert_path, key_path)
        with Server(("127.0.0.1", 0), Handler) as server:
            server.context, server.stall, server.hits = ctx, label == "stall", 0
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            env = dict(os.environ)
            if label == "epoch-zero":
                env["TEST_EPOCH_ZERO"] = "1"
            url = f"https://localhost:{server.server_address[1]}{path}"
            result = subprocess.run([str(binary), url], text=True, capture_output=True,
                                    timeout=8, env=env)
            server.shutdown()
            thread.join()
            assert result.returncode == (0 if success else 1), (label, result.stdout, result.stderr)
            assert "runtime error:" not in result.stderr, (label, result.stderr)
            assert "FD_LEAK" not in result.stdout
            if label in ("wrong-host", "expired", "future", "untrusted", "epoch-zero", "stall"):
                assert server.hits == 0, label
            if success:
                assert "TLS verified:" in result.stdout and "body_bytes=5" in result.stdout
            if label == "epoch-zero":
                assert "HTTPS blocked" in result.stdout
            if label == "stall":
                assert "error=110" in result.stdout
            print(f"PASS: {label}", flush=True)
    for url in ("http://localhost/", "https://user:password@localhost/", "https://localhost/\r\nX:1"):
        result = subprocess.run([str(binary), url], capture_output=True, timeout=5)
        assert result.returncode == 1
    print("PASS: 14 HTTPS cases, real TLS/parser, certificate rejection before HTTP, time gate, deadlines and descriptor cleanup")
    if "--stream" in sys.argv[4:]:
        for mode in range(6):
            with Server(("127.0.0.1", 0), Handler) as server:
                server.context, server.stall, server.hits = ctx, False, 0
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                path = "/stream401" if mode == 5 else "/stream"
                env = dict(os.environ, TEST_STREAM_URL=f"https://localhost:{server.server_address[1]}{path}",
                           TEST_STREAM_MODE=str(mode))
                result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=8, env=env)
                server.shutdown()
                thread.join()
                assert result.returncode == (0 if mode == 0 else 1), (mode, result.stdout, result.stderr)
                assert "FD_LEAK" not in result.stdout and "runtime error:" not in result.stderr
                if mode == 5:
                    assert "received=0" in result.stdout
                print(f"PASS: streaming TLS POST mode={mode}", flush=True)
    if "--mimo" in sys.argv[4:]:
        cert, key = make_cert("localhost", ca, ca_key)
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert_path, key_path)
        for case in ("ok", "chunked", "401", "429", "500", "length", "oversize", "json", "reflect", "redirect", "truncated"):
            with Server(("127.0.0.1", 0), Handler) as server:
                server.context, server.stall, server.hits, server.posts = ctx, False, 0, 0
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                env = dict(os.environ, TEST_MIMO_URL=f"https://localhost:{server.server_address[1]}/mimo{case}")
                result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=8, env=env)
                server.shutdown()
                thread.join()
                success = case in ("ok", "chunked")
                assert result.returncode == (0 if success else 1), (case,result.stdout,result.stderr)
                assert server.posts == 1 and server.hits == 1, (case,server.posts,server.hits)
                assert "sk-loopback-test-only" not in result.stdout
                assert "runtime error:" not in result.stderr and "FD_LEAK" not in result.stdout
                assert ("XiaoPai: Hello from fixture" in result.stdout) == success
                print(f"PASS: MiMo TLS POST {case}", flush=True)
    if "--live" in sys.argv[4:]:
        shutil.copy(app / "xiaopai_tls_ca.h", root / "xiaopai_tls_ca.h")
        command[command.index("-DXIAOPAI_HTTPS_TIMEOUT_MS=2000")] = "-DXIAOPAI_HTTPS_TIMEOUT_MS=60000"
        subprocess.run(command, check=True)
        result = subprocess.run([str(binary), "https://valid-isrgrootx1.letsencrypt.org/"],
                                text=True, capture_output=True, timeout=75)
        print(result.stdout, flush=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "runtime error:" not in result.stderr, result.stderr
        print("PASS: public endpoint with production ISRG Root X1 (host only)")
        if "--mimo" in sys.argv[4:]:
            result = subprocess.run([str(binary), "https://api.xiaomimimo.com/v1/models"],
                                    text=True, capture_output=True, timeout=75)
            print(result.stdout, flush=True)
            assert "TLS verified:" in result.stdout, result.stdout + result.stderr
            assert "status=401" in result.stdout, result.stdout + result.stderr
            assert "runtime error:" not in result.stderr and "FD_LEAK" not in result.stdout
            print("PASS: MiMo hostname/production CA chain, unauthenticated GET only; no model call")
