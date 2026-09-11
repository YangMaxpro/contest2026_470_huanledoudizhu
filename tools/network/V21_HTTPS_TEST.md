# V21 Verified HTTPS Diagnostic

Status: Ubuntu build and host tests passed; board HTTPS verification pending.
The user performs flashing and physical resets. No GitHub push was performed.

## Changes

- Suppress repeated netwatch down-state notifications and redundant address
  clearing while retaining disconnect-epoch checks for stale DHCP results.
- Add `xiaopai httpscheck [https://host/path]`, using the repository's Mbed TLS
  3.4.0 and existing HTTP parser. HTTP diagnostics remain unchanged.
- Require TLS 1.2, a trusted certificate chain, hostname/SNI, and certificate
  validity dates. No insecure override, redirects, or URL credentials.
- Seed a private CTR_DRBG directly from the CP-backed `/dev/random`; fail on
  errors or incomplete entropy reads. No host/platform entropy fallback.
- Limit body size to 32 KiB and socket operations to a 60-second deadline.
  DNS uses synchronous system resolver timeouts. Serialize HTTPS checks to
  limit simultaneous heap use. Contexts are heap allocated and released.

## Artifact

Ubuntu: `/home/yang/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v21.bin`

- Image size: 8388608 bytes.
- Image SHA256: `8dfca3f295b98be4054c09074b3cf52f42dd3fdb61f3d3445361c0b31d1a1fef`.
- AP SHA256: `c97f0a0f62ad3b8955011597c4626ea003544e1f256bc400e4b0ae310d56ec14`.
- AP raw/FLASH: 653120 bytes; encoded: 693940 bytes.
- Static RAM: 167624 bytes. XiaoPai task stack: 8192 bytes.
- v19 CP, bootloader, and all bytes outside AP preserved from v20.
- Partition payload, CRC, and padding verified against the raw CP/AP images.
- Source backup: `bk7258_package/v21-before.tar`.

## Trust And Time

The only embedded trust anchor is ISRG Root X1, sourced from Ubuntu package
`ca-certificates 20260601~22.04.1` at
`/usr/share/ca-certificates/mozilla/ISRG_Root_X1.crt`.
Its DER SHA256 is
`96bcec06264976f37460779acf28c5a7cfe8a3c0aae11a8ffcee05c0bddf08c6`.
Root validity: June 4, 2015 through June 4, 2035.
Default endpoint: `https://valid-isrgrootx1.letsencrypt.org/`.
Arbitrary HTTPS sites with other roots are not supported by this trust store.

The clock sanity gate rejects dates before January 1, 2025. This is not time
synchronization or authentication. Set accurate current UTC manually after
boot; do not set an arbitrary date just to bypass the gate. Certificate date
validation remains enabled. Automatic trusted time setup is not implemented.

## Host Verification

Passed with actual C implementation and UBSan where supported:

- Netwatch worker: repeated disconnect events log only once; DHCP retry,
  renewal, stale results, stop/start failures, and recovery cases.
- Entropy callback: short reads, EINTR, EOF/error, deadline and zeroization.
- Existing HTTP parser: 14 cases.
- Actual TLS adapter, Mbed TLS and HTTP parser: 14 HTTPS cases, including
  valid/chunked responses, wrong hostname, expired/future/untrusted certificate,
  redirect, truncated body, unauthenticated EOF, stalled handshake, unset
  clock, invalid schemes, credentials and control characters. Certificate
  rejection occurs before an HTTP request; descriptor cleanup is checked.
- Public default endpoint using production CA: TLS 1.2,
  ECDHE-RSA-AES128-GCM-SHA256, HTTP 200, 4067 body bytes (host only).

Run from `/home/yang/openvela`:

```sh
python3 contest2026_470_huanledoudizhu/tools/network/test_netwatch.py contest2026_470_huanledoudizhu/app/xiaopai/xiaopai_netwatch.c
python3 contest2026_470_huanledoudizhu/tools/network/test_tls_entropy.py contest2026_470_huanledoudizhu/app/xiaopai/xiaopai_tls.c
python3 contest2026_470_huanledoudizhu/tools/network/test_httpcheck.py apps contest2026_470_huanledoudizhu/app/xiaopai
python3 contest2026_470_huanledoudizhu/tools/network/test_httpscheck.py apps contest2026_470_huanledoudizhu/app/xiaopai cmake_out/.._contest2026_470_huanledoudizhu/.config --live
```

Logs: `bk7258_package/v21-ap-build.log` and
`bk7258_package/v21-https-host-test.log`.

## Board Steps

Flash the artifact in Ubuntu using the existing loader workflow. Then enter
`ap_console open`, configure Wi-Fi using interface `xiaopai`, and start
`xiaopai netwatch start`. Do not run `renew` while netwatch owns DHCP. Confirm
DHCP ready and `xiaopai httpcheck` first.

With the board still at 1970, `xiaopai httpscheck` must fail with the accurate
UTC instruction and a nonzero exit status, rather than sending an HTTP request.

In a separate Ubuntu terminal generate the current NSH clock-setting command:

```sh
LC_ALL=C date -u '+date -u -s "%b %d %H:%M:%S %Y"'
```

Execute the printed command promptly at the board's `nsh>` prompt, then:

```text
date -u
xiaopai rngcheck
xiaopai httpscheck
echo $?
xiaopai httpscheck
echo $?
uptime
```

Expect a verified TLS version/cipher, HTTP 200, and exit status 0. Body size
may change with the endpoint. Save the complete output on any failure. A
physical RST is not required for these checks.

Repeat a hotspot outage/recovery without manual reconnect or renew. Expect
one down-state log per continuous outage, cleared IPv4, then DHCP recovery
and another successful HTTPS request. Do not infer that this one test proves
long-duration reliability.

## Remaining Limits

This is a bring-up diagnostic, not production-ready TLS deployment. The
repository's Mbed TLS 3.4.0 is old; security maintenance/upgrade and review are
required before production use. No revocation checking, TLS 1.3, automatic
clock synchronization, persistent credentials, or cloud protocol integration.
Only IPv4 is supported; an asynchronously failed connect does not retry all
remaining DNS addresses. Bare TLS TCP EOF is deliberately rejected when an
authenticated close is required. Board heap/stack high-water usage and TLS
handshake latency remain unmeasured. Host success does not establish board
HTTPS success or entropy certification.
