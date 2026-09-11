# v38 RTSA worker lifetime fix

v37 reported running/preflight after its command returned. The launcher used
a detached pthread in the command's task group. NuttX sched/task/exit.c calls
group_kill_children on task exit, including detached pthreads. This is a
launcher defect, not evidence of a deadlock inside agora_rtc_init.

v38 uses task_create("rtsa_lifecycle", 90, 16384, ...) with a separate task
group, matching the existing voice/netwatch background workers. The owner
remains alive through SDK init/create/destroy/fini. Arguments live in static
storage and initialization remains once per boot. Status starts at queued;
preflight now means the worker actually entered its entry point.

## Verification

- Host worker test defers entry until after the command returns; checks
  status, duplicate rejection, stack/priority, failed spawn and preflight.
- Mock SDK lifecycle and failure cleanup tests passed.
- Full ARM GCC 13.4 build passed: raw AP 1,071,936 bytes, static RAM 175,440.
- Encoded AP 1,138,932 bytes fits the existing 0x121000-byte partition.
- CP, bootloader and data outside AP preserved against the v37 base image.
- CRC, padding and exact partial-update slice verified.
- Real board SDK execution remains unverified. No join, audio capture,
  credentials, paid API calls or automatic hardware flashing in this test.

The isolated v37 build profile/directory is reused for this v38 source fix:
`/home/yang/openvela/cmake_out/rtsa_probe_v37_gcc13`.
Normal firmware config/build is not changed.

## Flash and test

Exit miniterm with Ctrl+] first. In the Ubuntu loader directory run:

```sh
./bk_loader download -p 0 -b 1500000 -s 0x11000 \
  -i /home/yang/openvela/bk7258_package/openvela-cp-ap-update-v38-rtc-probe-at-0x11000.bin
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

Use the previously working download/reset procedure. Never write this partial
image at zero and do not chip-erase. Range: [0x11000, 0x286000), 2,576,384 bytes.
SHA256: 3736821b542390f00efe302946a00fce4cc9e00b245164699c08cfa019576714

Windows copy:
`C:/Users/yang/Desktop/openvela/openvela-cp-ap-update-v38-rtc-probe-at-0x11000.bin`.

At CP `$`, enter `ap_console open` once. At `nsh>`:

```text
rtsa_probe status
rtsa_probe init f458b56136964d83acc1053c3b133cd0
sleep 10
rtsa_probe status
xiaopai ipc status
ps
free
```

Only the public App ID is used. No certificate or token is needed.
Expected: v38, attempted=1, running=0, stage=done, result=0,
callback_error=0; heartbeat acknowledgments continue without failures.
Record heap before/after values; do not assume an increase is harmless.
If still running, collect status/ps rather than launching another probe.
Do not force-delete SDK threads. The command's exit code only reports launch;
the status command reports the lifecycle result.
