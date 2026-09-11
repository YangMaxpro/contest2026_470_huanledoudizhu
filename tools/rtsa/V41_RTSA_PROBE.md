# v41 cleanup boundary tracing

v40 completed all five pre-cleanup observations, entered fini and then reset
after heartbeat loss. No fatal diagnostic was captured. Root cause remains
unresolved; the absence of a fatal print is not proof that no fault occurred.

v41 retains the lifecycle sequence and adds at most 128 cleanup trace lines
across SDK threads. They identify thread ID, operation, object, caller and
result for condition waits, mutex/condition destruction, socket close, PSRAM
free and pthread exit. Tracing is enabled only upon entering fini; native
errno is preserved. No SDK messages, credentials or audio are printed.
It changes timing and is not a fix, benchmark or full backtrace. A begin line
without an end narrows the search, but cancellation, invalid arguments,
concurrent threads and the trace limit must be considered.

## Verification

Full ARM GCC build and host sync/network/runtime/worker tests passed.
Raw AP 1,073,472 bytes, encoded 1,140,564, static RAM 175,440.
CRC, padding, preserved CP/boot/data and exact update slice verified.
SDK cleanup on the board remains unverified. No auto flash, channel join,
cloud API request or recording was performed.

## Board test

Exit miniterm. In the Ubuntu loader directory:

```sh
./bk_loader download -p 0 -b 1500000 -s 0x11000 \
  -i /home/yang/openvela/bk7258_package/openvela-cp-ap-update-v41-rtc-probe-at-0x11000.bin
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

Use the established download/reset procedure. Do not chip-erase or write
this partial image at zero. Range [0x11000,0x286000), 2,576,384 bytes.
SHA256: 0eb441bcdecdf1db17a0e3a49a36f7249faf5e16b64b1d1a7ed9b1351c705b87

After flashing, cold power-cycle the board because v40's warm reboot showed
a PSRAM startup timeout. Confirm `PWC: v36 PSRAM ready` before starting.
At CP `$`, enter `ap_console open`; at `nsh>` run:

```text
rtsa_probe status
rtsa_probe init f458b56136964d83acc1053c3b133cd0
```

Capture the entire output for about 20 seconds, including all cleanup/fatal
lines and any reboot. Do not repeat init. If still responsive and not reset,
collect `rtsa_probe status`, `xiaopai ipc status`, and `ps`.

Matching ELF retained for caller symbolization:
`/home/yang/openvela/bk7258_package/nuttx-v41-rtc-probe.elf`.
Build directory remains the isolated `cmake_out/rtsa_probe_v37_gcc13`.
