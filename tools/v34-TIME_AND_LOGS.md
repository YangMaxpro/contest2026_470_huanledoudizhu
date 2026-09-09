# v34: Automatic NTP and Wi-Fi key log removal

After the first successful DHCP lease, the AP starts the NuttX NTP client with
DNS names (`0.pool.ntp.org`, `1.pool.ntp.org`, `time.cloudflare.com`). The
daemon polls while running and has bounded retries. Every successful DHCP
lease invokes the library's idempotent start, restarting a stopped daemon.
Check it with:

```text
xiaopai time status
```

The output reports the Unix timestamp, NTP sample count, and whether a sample
has been received. HTTPS/MiMo must still be attempted only after `sync=received`
and an accurate date; NTP is not a secure time-attestation mechanism.

The CP vendor WPA path no longer prints the negotiated transient key (`WPA:
TK ...`) to the serial console. Existing non-secret connection state logs are
unchanged. Reflash both AP and CP from the v34 image.

## Verified Build

AP and CP builds and the netwatch host regression passed. NTP status reports
previously received samples, not authenticated time or daemon liveness.
Hardware NTP/HTTPS acceptance remains pending. The default NTP transport is
unauthenticated UDP; existing TLS CA/hostname/date checks remain enabled.

Upgrade: `/home/yang/openvela/bk7258_package/openvela-cp-ap-update-v34-at-0x11000.bin`

Start 0x11000, size 2576384, exclusive end 0x286000. No chip erase. This
preserves the board's stored profile and calibration partitions.
SHA256: `5f4d6706ea59e2383142efc2e929dfd75729ef95d15d8edc164b5fdbc7a4be6e`.

```sh
./bk_loader download -p 0 -b 1500000 -s 0x11000 -i /home/yang/openvela/bk7258_package/openvela-cp-ap-update-v34-at-0x11000.bin
```

After boot auto-connect, enter AP console, wait about 30 seconds, then:

```text
xiaopai time status
date -u
xiaopai httpscheck
xiaopai ipc status
```

If samples remain zero, collect the status rather than assuming sync succeeded.
No Wi-Fi save or manual date command is needed for this acceptance test.

Build sources/log backup: `/home/yang/openvela/bk7258_package/time-v34-Skeboz/`.
Full-image SHA256: `ddbb8646d414938a68ef1ac89b7f592d91372bab1ab4cb72bd9b87a6e453eb7e`.
AP raw 703296 bytes, CP raw 992608 bytes. Full-image bytes outside firmware
match the v33 base file; use the partial upgrade to preserve live board data.
