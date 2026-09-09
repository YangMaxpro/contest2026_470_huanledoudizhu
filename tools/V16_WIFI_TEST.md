# V16 Wi-Fi Test Commands

V16 adds PROCFS, mounts it at `/proc` after mailbox startup, and explicitly
enables NSH `ifconfig`, `ifup` and `ifdown`. The v15 Wi-Fi driver is unchanged.
The base CP, bootloader and data outside the AP partition remain unchanged.
No association, DHCP or ping success is claimed before hardware testing.

Build and packaging verified on 2026-09-07:

- Image size: 8388608 bytes; AP encoded size: 398548 bytes.
- SHA256: `31246fae6b4c3b714143628b23ff1e6f071f09551b4438c03833c09e442f7942`.
- FLASH used: 375104 bytes; static RAM: 158520 / 344064 bytes.
- Final map contains `cmd_ifconfig`, `cmd_ifup`, `cmd_ifdown`, `nx_mount`,
  `wapi_main`, `renew_main` and `ping_main`.
- All four packager tests passed; non-AP bytes compared identical to v15.
- Still pending: runtime PROCFS mount, router association, DHCP and ping.

The need for this change was confirmed by the user's v15 log: `wlan0`
registered and shared-channel netprobe succeeded, but `ifconfig` was absent.

## Flash From Ubuntu

Exit miniterm with Ctrl+] before flashing. The user handles flashing and RST.

```sh
cd ~/桌面/BEKEN_BKFIL_V2.1.11.8_20240509
./bk_loader download -p 0 -b 1500000 -g 60 -s 0x0 \
  -i ~/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v16.bin
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

At the CP `$` prompt: `ap_console open`.
At `nsh>`, first check `help` and `ifconfig`. Do not proceed if either
`ifconfig` or `ifup` is still missing, or `/proc/net` cannot be opened.

## Join A Router

Use a 2.4 GHz WPA2-Personal/CCMP network. Replace placeholders locally.
Do not share the password or include it in published serial logs.

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

Run commands individually. On an error, stop, run `echo $?` immediately,
and retain the output rather than repeatedly resetting the board.

An interface marked available is only registered, not necessarily connected.
Confirm the requested SSID, an AP-side IPv4 lease and gateway in `ifconfig`,
then run `ping -c 4 GATEWAY_IP` with that actual gateway. The CP's own IP is
not evidence of AP DHCP success. Check uptime and LEDs/demo again afterward.
