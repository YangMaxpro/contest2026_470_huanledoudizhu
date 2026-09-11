# V20 Runtime Wi-Fi Recovery

Status: built, host-tested, and one hotspot outage/recovery cycle verified
by the user on hardware. No automatic flashing or GitHub push was performed.

Hardware evidence: loss of carrier cleared IPv4/mask/gateway; recovery gave
`attempts=2 leases=2 last_error=0`, CP state 3, a RUNNING interface with DHCP
address, and HTTP 200 with 559 body bytes and exit status 0. Uptime was 3:22.
Repeated down-state messages were observed and are addressed in v21. This
does not establish long-duration lease renewal or reboot persistence.

## Evidence And Fix

V19 hardware achieved RNG and HTTP success, and uptime 50:23 after a hotspot
outage. However, CP reported disconnected, and reissuing the ESSID did not
restore association. AP retained its old address despite lost carrier.

The driver sent SET_AUTO_RECONNECT=false, but kept the STA role STARTING
after a disconnect while expecting CP reconnect. New connect requests were
rejected as busy while that role remained allocated.

- Send SET_AUTO_RECONNECT=true. CP uses the vendor reconnect implementation;
  its current config has zero reconnect-count limit (vendor meaning: always
  reconnect). Credentials remain in RAM, not new persistent storage.
- An explicit STA connect first stops the previous STA role; failed stop
  aborts the restart. Other roles are not forcibly replaced.
- Add `xiaopai netwatch start|stop|status`, opt-in once per boot. This task
  owns IPv4/DHCP and DNS on the single-interface board until stopped.
- Poll carrier every second and track disconnect events, including down/up
  events occurring between polls. Clear obsolete IP/mask/gateway, reset DNS
  to system defaults, reacquire DHCP on recovery, and request a new lease at
  half the lease lifetime using the existing DHCP library.
- DHCP failures clear partial configuration and retry after 5/10/20/30 seconds
  (30-second cap). No tight retry loop and no device reboot.
- Discard a DHCP result if a disconnect or stop occurred during the request.
  The existing library writes the offered address before returning, so the
  monitor clears it when rejecting the result; application is not an atomic
  transaction with link events. Carrier gating prevents sends while down.
- Stop is cooperative. It can wait for the current DHCP library operation
  (configured receive timeout/retries), then clears IPv4/DNS and releases
  ownership. It does not disconnect the radio. Check status before running
  `renew` or starting another address manager.

No boot-time saved Wi-Fi credentials, TLS, cloud, or audio changes. Initial
Wi-Fi setup still uses wapi. Do not use this single-interface DHCP monitor
for static IPv4, SoftAP, or multiple-interface routing.

## Artifact

Ubuntu: `/home/yang/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v20.bin`

- Size: 8388608 bytes.
- SHA256: `50305b6a66676220be545f78dadc86727e554a6c2b1b01a01e16affa8449fefe`.
- AP SHA256: `dadc8d81d9478b5537c5642b51b7168f10a3f99ee057976de25e2d6bea0603ec`.
- AP raw/FLASH: 404800 bytes; encoded: 430100 bytes; static RAM: 158576 bytes.
- v19 CP and every byte outside AP are preserved. Partition payload, CRC and
  padding verified against the saved raw images.
- Pre-change sources: `bk7258_package/v20-before.tar`.
- Incremental driver patch: `v20-wifi-reconnect.patch`, relative to NuttX.
  App additions and defconfig live in the contest tree.

Host checks passed using actual C functions with stubs and UBSan:

```sh
python3 test_wifi_reconnect.py NUTTX/arch/arm/src/bk7258
python3 test_netwatch.py CONTEST/app/xiaopai/xiaopai_netwatch.c
python3 test_cp_random_protocol.py CP_CIF_CNTRL AP_WIFI
python3 test_httpcheck.py APPS_DIR XIAOPAI_APP_DIR
```

Coverage includes automatic-reconnect command, link transitions, manual
restart, stop/command failures, late connect events, role isolation, lease
refresh, backoff, stale DHCP response, stop during request, malformed lease,
duplicate start and task/registration failure. HTTP's 14 cases passed again.
Stub tests do not prove CP radio behavior or RTOS concurrency on hardware.

## Hardware Steps

The user flashes in Ubuntu, with miniterm closed:

```sh
cd ~/桌面/BEKEN_BKFIL_V2.1.11.8_20240509
./bk_loader download -p 0 -b 1500000 -g 60 -s 0x0 \
  -i ~/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v20.bin
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

Enter `ap_console open`, then configure the initial Wi-Fi connection in NSH.
Replace placeholders locally; do not publish the password.

```text
ifup xiaopai
wapi mode xiaopai WAPI_MODE_MANAGED
wapi psk xiaopai "YOUR_PASSWORD" WPA_ALG_CCMP
wapi essid xiaopai "YOUR_SSID" WAPI_ESSID_ON
xiaopai netwatch start
sleep 10
xiaopai netwatch status
xiaopai netprobe
ifconfig
xiaopai httpcheck
echo $?
```

Do not run `renew` while netwatch owns DHCP. Expect `netwatch: DHCP ready`,
RUNNING with an address, and HTTP 200. If association is still pending,
inspect netprobe/status instead of assuming a fixed ten-second deadline.

Turn the hotspot off for 20 seconds and inspect netprobe, ifconfig and uptime.
Expect no carrier and old IPv4 cleared. Turn the same hotspot on again; do not
reissue wapi, renew, or RST. Allow up to 90 seconds for CP scans and DHCP, then:

```text
xiaopai netwatch status
xiaopai netprobe
ifconfig
xiaopai httpcheck
echo $?
xiaopai rngcheck
echo $?
uptime
```

Expect CP state 3, SSID restored, a new DHCP success count, HTTP/RNG return 0,
and continuous uptime. Repeat the outage twice, including one longer outage.
Hotspot subnet/address changes are allowed; inspect the newly acquired IP.
Report failure logs rather than repeatedly reflashing.

Additional tests: explicit ESSID restart while disconnected; intentional
`ifdown xiaopai` must stay down; `netwatch stop` must eventually show stopped.
Reboot credential persistence and long-duration lease behavior are not yet
hardware-verified. No RST is needed for these commands. When requesting a
physical reset, wait for the user's confirmation before dependent actions.
