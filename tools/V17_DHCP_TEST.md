# V17 AP-Owned IPv4

## Observed On V16

User hardware log confirms `ifconfig`, `ifup`, association, RSSI -42 dBm,
ARP receive, and RUNNING wlan0. AP DHCP failed and its IPv4 remained 0.0.0.0.
No Wi-Fi credentials are recorded here.

The legacy CP's `cif_filter_check_bk_filter()` reserves UDP destination ports
67/68/53 for CP. Its STA stack also runs DHCP. This conflicts with AP-owned
IPv4; the DHCP response path cannot reach the OpenVela client as configured.
This source-level defect is fixed below, but additional TX/RX issues may
still surface in hardware testing.

## Changes

`v17-cp-ipv4.patch` captures changes to the existing SDK:

- Add `CONFIG_WIFI_VNET_AP_IPV4`, requiring controller and direct-push RX.
- Enable it in `projects/app_ab/cp/config/bk7258/config` (one additional line,
  deliberately not exporting unrelated pre-existing project configuration).
- Forward STA ARP/IPv4 to AP when the host is active. EAPOL stays on CP;
  other virtual interfaces and legacy mode retain their existing policy.
- Disable CP `sta_ip_start()` and unsolicited STA ARP reply generation.
- Notify AP of association using its link-event 0x12 / STA_CONNECTED 2 ABI,
  before any DHCP lease exists. Do not fabricate an IPv4-acquired event.
- AP legacy event IDs now match CP: disconnect=2, start AP=3, scan=7.
  Extended-CP event IDs remain conditional on the existing extension option.

Pre-edit SDK source backup on Ubuntu:
`/home/yang/openvela/bk7258_package/v17-cp-before.tar`.
Existing boot, mailbox, clock and console changes were preserved.

## Verification

CP built with `bekencorp/armino-idk:1.5` using:

```sh
make bk7258_cp PROJECT=app_ab BUILD_DIR=/home/yang/bk7258_sdk/projects/app_ab/build
```

Container mounts the SDK at the same absolute path. AP built using the v16
OpenVela board config. CP build compiled cif_wifi_dp.c, notify.c and net.c;
generated config enables AP IPv4 and retains CPU1 480 MHz/direct-push RX.
Disassembly confirms `sta_ip_start` returns without starting CP DHCP.

`test_cp_ipv4_forwarding.py` compiles the actual receive function in both
ownership modes and checks IPv4/ARP routing, EAPOL retention, other VIF,
inactive/no host, failed-send release and successful ownership transfer.
It passed. Four packager tests also passed. Neither test proves radio TX or
DHCP negotiation on hardware.

Image: `/home/yang/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v17.bin`

- Size: 8388608 bytes.
- SHA256: `fdfce1c494c826d7db50de60bbbb8a576d302f3255fe2f4ced9cccb3766839a6`.
- CP encoded bytes: 1053660; AP encoded bytes: 398548.
- CP raw SHA256: `0b6306f35fefdcd6ca1c332a35f33e30d42e41baa9d0d801a6c8afbfcf7d88d4`.
- Base v16. Only CP/AP partitions changed. Bootloader and all data after
  0x286000 compared identical to v16.
- No flashing or GitHub push performed by the agent.

## Hardware Test

User flashes v17 in Ubuntu with the same BKFIL flags as v16. After opening
the AP console, repeat the WPA2 connection commands from V16_WIFI_TEST.md.
Then run `xiaopai netprobe`, `renew wlan0`, `ifconfig` individually. Stop on
errors and save the output; do not copy passwords into shared logs.

Acceptance: AP obtains a valid IPv4/netmask/gateway, `ping -c 4 GATEWAY_IP`
succeeds using the actual gateway, and heartbeat/LED/demo behavior remains
stable. Disconnect/reconnect must also be tested. Hardware results pending.

The probe still prints `v15 shared netdev command channel`: that labels the
probe implementation, not the complete firmware version.
