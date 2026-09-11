# v40 cleanup isolation diagnostic

v39 passed preflight, init, create and destroy, then printed step 5 and reset
after CP observed 8000 ms without heartbeat. No SDK return was logged.
This does not establish a root cause. Archive disassembly shows fini waits
for message-queue destruction; service cleanup includes explicit abort paths.

v40 adds a five-second HOLD (step 8) before fini, printing once per second.
It privately redirects the SDK abort import to a native diagnostic that
prints the caller address, flushes output, waits 20 ms, then calls native
abort. Assertion diagnostics print only a caller address and source line.
It does not bypass SDK cleanup, extend heartbeat timeout or enable audio.
Timing is intentionally changed; this is not a fix or performance benchmark.

Host lifecycle, worker and libc tests pass; libc tests confirm fatal paths
still terminate with SIGABRT and do not print supplied private strings.
Full ARM build: AP raw 1,072,960 bytes; encoded 1,140,020; static RAM 175,440.
Isolated v37 build directory reused; baseline remains unchanged.

## Flash

Exit miniterm first. In the existing Ubuntu loader directory:

```sh
./bk_loader download -p 0 -b 1500000 -s 0x11000 \
  -i /home/yang/openvela/bk7258_package/openvela-cp-ap-update-v40-rtc-probe-at-0x11000.bin
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

Use the established board download/reset procedure. Do not erase the chip
or flash this partial image at zero. Partial range [0x11000,0x286000),
2,576,384 bytes. CP and out-of-AP bytes are preserved from v39.
Partial SHA256: 8779e3378036978d6dc85d16b46f5f7cc2dbd352a6860e9df008e4270c3d7428

At CP `$`: `ap_console open`. At `nsh>`:

```text
rtsa_probe status
rtsa_probe init f458b56136964d83acc1053c3b133cd0
```

Wait 20 seconds and capture all output, including observations, fatal caller
addresses and reset messages. Do not repeat init. If no reset occurs, obtain
`rtsa_probe status`, `xiaopai ipc status`, and `ps`.
No certificate, token, channel join, paid request or microphone is involved.

An abort caller must be symbolized using the matching v40 ELF, never an ELF
rebuilt later. The archived ELF is
`/home/yang/openvela/bk7258_package/nuttx-v40-rtc-probe.elf`.
Normalize the Thumb return address and inspect the preceding call as needed.
Absence of a fatal print does not exclude abort or a hardware exception,
because the mailbox console itself may be unavailable during failure.
