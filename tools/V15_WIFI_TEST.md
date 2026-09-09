# V15 Wi-Fi Bring-Up

Status: built and host-tested on 2026-09-07; hardware testing pending.
This is not a verified Wi-Fi release. Do not publish it as one.

Hardware follow-up on 2026-09-07: the user confirmed netdev initialization,
`wlan0` registration, shared-channel netprobe, and interface availability.
`ifconfig` was missing because PROCFS was disabled; `ifup/down` were disabled
by the same dependency. Association, DHCP and ping remain untested. Use the
v16 command/configuration fix for the next network test, not v15.

## Image

Ubuntu image:
`/home/yang/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v15.bin`

- Size: 8388608 bytes.
- SHA256: `c2bcb08a444431417dd11740039f69f78d05148c29133c0cc413b2c4a372616b`
- AP binary SHA256: `ce8fb9b865f5573d97958255f3a5aecf835c748886b4acda14c2dec7ac1b6f26`
- Base: v14, SHA256 `e94ef501714cf70ed8a91c5ca69229aeb7450e95e28dad7c87f04e2963d0e0b9`.
- AP partition: `[0x165000, 0x286000)`, with 366452 encoded bytes.
- All bytes outside the AP partition compared identical to v14.
- CP, bootloader, calibration and environment data are preserved from v14.

## Changes And Limits

- Register a NuttX Wi-Fi netdev using the CP mailbox command and data channels.
- Keep legacy CP compatibility: disable unsupported scan-page, country and
  SoftAP extensions. Connect to a known SSID; do not use `wapi scan` in v15.
- Route `xiaopai netprobe` through the full driver's serialized command path.
  The standalone v14 probe cannot replace the driver's receive handler.
- Enable HP/LP work queues, IPv4, DHCP `renew`, `wapi`, and `ping`.
- Disable NSH automatic network initialization with an empty SSID.
- `xiaopai status` reports interface registration, not internet reachability.
- Cloud conversation is not implemented; the demo remains a local simulation.

## Build And Package

Run in `/home/yang/openvela`. After a defconfig change, explicitly reset the
generated configuration before building; an incremental build alone retains
the previous `.config`.

```sh
./build.sh ../contest2026_470_huanledoudizhu/board/contest_board/configs/bk7258-devkit/nsh --cmake resetconfig
./build.sh ../contest2026_470_huanledoudizhu/board/contest_board/configs/bk7258-devkit/nsh --cmake
```

The packager is also installed in `bk7258_package/` on Ubuntu. Omitting `--cp`
preserves the base image's CP. It refuses to overwrite an existing output.

```sh
python3 bk7258_package/make_bk7258_linear_crc_image.py \
  --factory bk7258_package/openvela-correct-linear-crc-8MB-v14.bin \
  --ap cmake_out/.._contest2026_470_huanledoudizhu/nuttx.bin \
  --output bk7258_package/openvela-correct-linear-crc-8MB-v15.bin
```

Build passed: FLASH 344896 bytes, static RAM 158512 / 344064 bytes.
Final symbol map contains `bk7258_wifi_initialize`, one `bk7258_wifi_probe`,
`wapi_main`, `renew_main`, and `ping_main`. Packager regression tests (4) and
legacy probe parsing/ownership tests passed. These are not full-driver hardware
or network packet-path tests.

## User-Operated Flashing

Exit miniterm with Ctrl+] first. The user performs flashing and any RST action.
When an RST action is requested, wait for the user's explicit confirmation.

```sh
cd ~/桌面/BEKEN_BKFIL_V2.1.11.8_20240509
./bk_loader download -p 0 -b 1500000 -g 60 -s 0x0 \
  -i ~/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v15.bin
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

## Hardware Gates

At the CP `$` prompt run `ap_console open`. At `nsh>` run:

```text
help
ifconfig
xiaopai netprobe
xiaopai status
uptime
```

Expect `BK7258 Wi-Fi netdev initialized`, a `wlan0` interface, and a probe
showing `v15 shared netdev command channel`. Stop and retain the boot log if
initialization fails; do not repeatedly reset or restore factory firmware.

Once wlan0 exists, use a 2.4 GHz WPA2-Personal/CCMP access point. Replace the
placeholder SSID and password locally; do not publish credentials in logs.

```text
ifup wlan0
wapi mode wlan0 WAPI_MODE_MANAGED
wapi psk wlan0 "YOUR_PASSWORD" WPA_ALG_CCMP
wapi essid wlan0 "YOUR_SSID" WAPI_ESSID_ON
sleep 5
xiaopai netprobe
renew wlan0
ifconfig
```

Use the actual gateway from `ifconfig` in `ping -c 4 GATEWAY_IP`.
Acceptance requires association, an AP-side DHCP lease, successful gateway
ping, and at least 10 minutes without heartbeat reset. A CP IP address alone
does not prove AP DHCP or packet transport works. Run LED commands and
`xiaopai demo` again to check the existing baseline. Save failure output and
`echo $?` immediately after any failed command.
