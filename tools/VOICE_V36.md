# v36 PSRAM startup ordering

Supersedes v35 upgrade instructions. v35 attempted ordinary PWC PSRAM ON
inside the PWC bootstrap, before HW_CTRL and UART READY. The mailbox rejected
it with -ENOLINK (-67); returning early prevented console readiness.

v36 separates bootstrap from PSRAM initialization. Ordering is PWC boot-ready,
HW_CTRL heartbeat, mailbox READY, then PSRAM power/allocator initialization.
PSRAM failure is nonfatal for console/network initialization; voice allocation
still fails closed. Voice implementation remains v35 (status reports v35).
Successful PSRAM startup prints `PWC: v36 PSRAM ready; dedicated AP heap online`.

Verification: AP build, real late-init sequence host fault injection, heartbeat
regression, image CRC and unchanged non-CP/AP bytes passed. CP unchanged.
Hardware PSRAM/voice success is not yet confirmed. No flashing or paid API calls.

Ubuntu upgrade, after closing miniterm; use usual hardware download procedure:

```sh
cd ~/桌面/BEKEN_BKFIL_V2.1.11.8_20240509
./bk_loader download -p 0 -b 1500000 -s 0x11000 -i /home/yang/openvela/bk7258_package/openvela-cp-ap-update-v36-at-0x11000.bin
```

No chip erase; do not use address zero. Image spans [0x11000,0x286000),
2576384 bytes. Wi-Fi profile/boot/calibration outside the update remain intact.
SHA256: 15b543d8aabfab23c5ececf797ee3092d4b1623869aef8d612f7e7ea0751ef73

Collect boot log first. Enter `ap_console open` from CP `$`, then
`xiaopai ipc status` and `xiaopai time status`. Confirm PSRAM ready before
resuming voice. Do not share API keys.
