# v37 RTSA local lifecycle diagnostic

This is not working cloud voice firmware. It tests actual RTSA startup and
resource cleanup on OpenVela without joining a channel or enabling audio.
The MiMo text/voice commands are disabled in this diagnostic configuration.
Wi-Fi persistence, NTP, heartbeat and local audio diagnostics are retained.

## Verified before handoff

- Full isolated ARM GCC 13.4 build passed with recursive mutexes and loopback.
- FLASH used: 1,071,936 bytes; static RAM: 175,440 of 344,064 bytes.
- Encoded AP: 1,138,932 bytes within the unchanged 0x121000-byte partition.
- Host tests: SDK call order/failure cleanup; worker preflight, priority,
  stack size, failed-launch handling and once-per-boot protection.
- Existing synchronization, runtime, network, libc, loopback and HAL tests
  passed during port work. Real board runtime still requires verification.
- CRC, base CP preservation, bootloader and out-of-partition bytes verified.
- Local and Ubuntu partial-update SHA-256 match.

## Artifacts

Ubuntu partial update:
`/home/yang/openvela/bk7258_package/openvela-cp-ap-update-v37-rtc-probe-at-0x11000.bin`

Windows copy:
`C:/Users/yang/Desktop/openvela/openvela-cp-ap-update-v37-rtc-probe-at-0x11000.bin`

Partial size: 2,576,384 bytes. Write range: `[0x11000, 0x286000)`.
SHA-256: `228c8d837cda884a3c604519f372d42a156963d79b09459c350d741fe676395d`.

Full reference image (not the flashing file for the instructions below):
`/home/yang/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v37-rtc-probe.bin`

Full image SHA-256:
`a3560f207946399bdb45e61b13131fffc951505d6d465be210f3fe0c44db9483`.

## Board test

Quit miniterm first with Ctrl+]. Run in the Ubuntu loader directory:

```sh
./bk_loader download -p 0 -b 1500000 -s 0x11000 \
  -i /home/yang/openvela/bk7258_package/openvela-cp-ap-update-v37-rtc-probe-at-0x11000.bin
```

Use the same board download/reset procedure as v36. Do not chip-erase and do
not write this partial image at zero. No flashing/reset was done by the agent.

Reconnect:

```sh
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

Only at the CP `$` prompt enter `ap_console open`. At `nsh>` run:

```text
rtsa_probe status
xiaopai ipc status
rtsa_probe init f458b56136964d83acc1053c3b133cd0
sleep 5
rtsa_probe status
xiaopai ipc status
free
```

The identifier above is the public App ID, not a key. Do not enter any App
certificate or Token for this test.

Expected: attempted=1, running=0, stage=done, result=0, callback_error=0,
and heartbeat attempts/acks continue increasing without failures or reboot.
Collect the PSRAM before/after byte counts; an increase requires investigation,
not an automatic quality pass. The SDK may retain global allocation state.

If still running, inspect status/heartbeat once more after 10 seconds. Do not
start a second probe or force-delete an SDK worker. Capture output and reboot
if it remains stuck. After any SDK attempt, reboot before another init test.
An `init` command exit status of zero only means its worker was launched.
`rtsa_probe status` holds the actual result.

Rollback, if needed, uses the existing v36 partial image at the same 0x11000
address. Confirm the v36 file exists before selecting it. Do not erase saved
Wi-Fi configuration or change bootloader offsets to troubleshoot SDK startup.

## Reproduce the isolated configuration

Baseline input:
`board/contest_board/configs/bk7258-devkit/nsh/defconfig`.
Generated config: `/home/yang/openvela/rtsa-probe-v37-config`.
Build: `/home/yang/openvela/cmake_out/rtsa_probe_v37_gcc13`.
SDK: `/home/yang/bk7258_sdk/ap/components/bk_thirdparty/agora-iot-sdk`.

The generation tool refuses an existing output directory. Configure CMake with
that BOARD_CONFIG and XIAOPAI_RTSA_SDK_DIR, and put the OpenVela ARM GCC 13.4
bin directory first in PATH. The default system ARM compiler is a different
version. Build through CMake/Ninja; Make intentionally rejects this probe option.
