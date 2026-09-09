# V18 Interface Name And HTTP Check

Image generated in Ubuntu:
`/home/yang/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v18.bin`.
Size 8388608 bytes; SHA256
`182e78af3ca6df72c5bcb38d1c5b4057143adc1ca7d518e1d104311e28d0c16d`.
AP encoded size 410516 bytes; all non-AP bytes compared identical to v17.
Build passed (FLASH 386368 bytes, static RAM 158520 bytes), final map includes
`xiaopai_httpcheck`, `webclient_perform` and `cmd_ifconfig`. Config confirms
`CONFIG_BK7258_WIFI_IFNAME="xiaopai"`. User hardware logs confirm the rename,
DHCP on `xiaopai`, and two completed HTTP requests: status 200, body 559 bytes,
with final `echo $?` equal to 0. HTTPS remains unverified and is not enabled.

## Verified Baseline

User logs from v17 confirm association, AP DHCP, gateway ICMP 20/20,
external ICMP 19/20, DNS lookup with exit status 0, uptime over 12 minutes,
and local demo exit status 0. Occasional external loss and old/duplicate
ICMP replies remain unexplained; do not claim loss-free networking or TLS.

## Changes

- Interface renamed from `wlan0` to exactly `xiaopai` via
  `CONFIG_BK7258_WIFI_IFNAME`. MAC, chip ID, and hotspot SSID are unchanged.
- Driver registration and application interface lookup share that setting.
- Added `xiaopai httpcheck [http://host/path]`, default `http://example.com/`.
  Uses the existing NuttX HTTP parser and nonblocking sockets. No body files,
  credentials, redirects, HTTPS, or AI traffic. 2 KiB I/O buffer, 32 KiB body
  limit; HTTP 2xx plus a completed response is success.
- Socket processing uses a monotonic 30-second deadline. DNS is synchronous
  inside the library and cannot be interrupted by this deadline; it retains
  the system resolver's existing timeout/retry settings.
- Fixed HTTP nonblocking resume for CHUNKED_ENDDATA, CHUNKED_TRAILER and
  WAIT_CLOSE. Without these states in the receive-loop gate, resuming after
  EAGAIN can spin instead of processing data or returning to the caller.
  Patch: `v18-webclient-resume.patch`, relative to the apps repository.

The host test `test_httpcheck.py APPS_DIR XIAOPAI_APP_DIR` builds the real
wrapper and HTTP parser and uses a Linux loopback server. Fourteen cases
cover success, fragmented chunked response, 204, 404, redirect suppression,
truncation, large body, malformed response, oversized headers, stall timeout,
invalid/credential URLs and connection refusal. Every case checks for leaked
file descriptors. All passed; this does not prove TCP works on the board.

## Hardware Test

After user-operated flashing and serial `ap_console open`, verify `ifconfig`
shows `xiaopai` (not `wlan0`). Replace the password locally; do not share it.

```text
ifup xiaopai
wapi mode xiaopai WAPI_MODE_MANAGED
wapi psk xiaopai "YOUR_PASSWORD" WPA_ALG_CCMP
wapi essid xiaopai "YOUR_SSID" WAPI_ESSID_ON
sleep 5
renew xiaopai
ifconfig
xiaopai status
xiaopai httpcheck
echo $?
```

Expected final HTTP output: `HTTP check passed: status=200 body_bytes=...`
and exit code 0. A redirect/non-2xx still proves that some HTTP response was
received, but this strict test returns failure. HTTPS is rejected, not tested.
Do not send secrets over this plain-HTTP diagnostic command.

Repeat `httpcheck`, `uptime` and the LED/demo checks after the first success.
If it fails, retain status, byte count, error and surrounding serial output.
No RST is needed for commands; only perform hardware reset when explicitly
requested, then confirm before the agent continues dependent work.
