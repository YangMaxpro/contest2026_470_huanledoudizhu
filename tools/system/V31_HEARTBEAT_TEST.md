# V31 Heartbeat Console Isolation

Status: host fault-injection tests, firmware build, and image CRC verification
passed. Hardware reset root cause and long-duration stability remain unverified.

Hardware follow-up: idle heartbeat snapshots had matching attempts/ACKs and
zero errors, but plain `ps` still stopped after PID 9 and caused an 8-second
heartbeat reset. Thus v31 did NOT eliminate the observed reset. On the same
firmware, `nsh -c "ps"` completed, listing the boot shell with a 2000-byte
adjusted stack and the separate shell with a 4040-byte adjusted stack. See
V32_NSH_STACK.md for the boot-stack correction and remaining validation.

## Evidence and Scope

The board lost its AP console and reset with an 8000 ms CP heartbeat gap while
printing `ps`, without a new HTTPS request. The rebooted board had 141816 bytes
of free heap; this is not a measurement of the pre-failure heap or task stacks.

The synchronous HW_CTRL wait path called `bk7258_mailbox_dump_stats()` before
returning a timeout. This uses blocking `printf` over the same mailbox console.
If console writes stall, the heartbeat cannot return to its next iteration.
This is a code-level blocking risk, not proof of the original trigger.

- HW_CTRL timeout now returns without console output. PWC diagnostics unchanged.
- The active heartbeat worker no longer prints startup/first-three/error logs.
  Its interval remains 2 seconds, priority 110, stack 1536 bytes and response
  wait 600 ms. CP code and its reset threshold are unchanged.
- `xiaopai ipc status` copies live worker and transport counters, then prints
  three lines from the command task. The snapshot performs no mailbox request,
  console write, heap allocation or sleeping mutex acquisition.
- Attempts and valid ACKs are distinct. Failures count failed synchronous sends;
  a late valid ACK can coexist with a failed attempt. `sending` includes lock,
  submission and response wait; it does not prove a frame reached the wire.
- Ages/durations use monotonic ticks, not UTC. `since_ack` is meaningful only
  when `ack` is nonzero. Counters are RAM-only and reset on reboot.
- The older unused `bk7258_ipc_heartbeat_poll()` is not enabled or changed.
- No Wi-Fi persistence/autostart, microphone settings, cloud key handling or
  TLS policy changes are included.

## Software Verification

```sh
python3 contest2026_470_huanledoudizhu/tools/system/test_heartbeat.py nuttx/arch/arm/src/bk7258
cmake --build cmake_out/configs_nsh -j8
```

Host tests compile the real heartbeat source and mailbox wait loop with UBSan
and warnings as errors. Console writes during runtime fail the test. Cases:
queued-without-ACK timeout at 600 ms, busy channel, malformed/missing ACK,
repeated failures followed by recovery, thread creation failure, counter
snapshots, and preservation of PWC timeout diagnostics. These are stubbed
hardware/transport tests, not full mailbox recovery or scheduler proofs.

Build: FLASH 693056 bytes; static RAM 176496 / 344064 bytes.

Image on Ubuntu:
`/home/yang/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v31.bin`

SHA256: `8f58f8fe49350be62abe9e326a4a42bcad71d06ac57a8e54fa0aae7a3fdb64d4`

Base is v30. CP matches the existing v19 CP binary. Bootloader and all bytes
outside CP/AP match the base. Previous source backup on Ubuntu:
`/home/yang/openvela/bk7258_package/heartbeat-v31-7IXF7p/before.tar.gz`.

## Manual Hardware Check

No automatic flashing or serial writes were performed. Exit miniterm before
using the loader. A full-image flash can replace stored device data with data
from the image; this is the existing test-board workflow, not a settings backup.

```sh
cd ~/桌面/BEKEN_BKFIL_V2.1.11.8_20240509
./bk_loader download -p 0 -b 1500000 -g 60 -s 0x0 -i /home/yang/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v31.bin
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

At CP `$`, run `ap_console open`. At AP `nsh>`, without configuring networking:

```text
xiaopai ipc status
sleep 10
xiaopai ipc status
```

Expect attempts and ACKs to increase, with failures remaining zero. `sending`
may be 0 or 1 depending on snapshot timing. Short counter output is intentional;
do not run repeated `ps`/cloud requests as the initial check. If link-down or
reset recurs, preserve the complete surrounding log. Passing this check does
not establish that the original reset has been eliminated.
