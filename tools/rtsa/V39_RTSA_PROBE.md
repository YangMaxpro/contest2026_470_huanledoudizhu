# v39 RTSA checkpoint diagnostic

## Board evidence

v38 init was followed twice by AP heartbeat loss and CP reset. In the first
attempt the console reported AP link down; CP subsequently reported RX IPC
send failures. Both CP heartbeat timeouts were 8000 ms. There was no AP fault
PC/backtrace or SDK stage output, so the exact root cause remains unknown.
The absence of later status is not proof of a specific SDK init deadlock.

## Changes and limits

Add checkpoints before loopback readiness, PSRAM allocation/free, heap stats,
and each SDK lifecycle call. Add SDK native-thread creation result logs.
Checkpoint output is flushed, followed by 20 ms to allow the mailbox console
to drain. This changes timing and is diagnostic only, not a latency benchmark.
No vendor log messages, App certificates, tokens or audio are printed.
Heartbeat timeout, worker priorities, buffers and network settings unchanged.
This firmware does not join a channel or invoke a paid cloud operation.

Host worker/runtime regression tests and full ARM build passed. Raw AP size
1,072,448 bytes, encoded 1,139,476 bytes; static RAM 175,440 bytes. Actual board
runtime is not verified. The isolated v37 build directory is reused.

## Flash

Exit miniterm first. In the Ubuntu loader directory:

```sh
./bk_loader download -p 0 -b 1500000 -s 0x11000 \
  -i /home/yang/openvela/bk7258_package/openvela-cp-ap-update-v39-rtc-probe-at-0x11000.bin
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

Keep the established download/reset procedure. No chip erase. Never write
this partial image at zero. It covers [0x11000,0x286000), 2,576,384 bytes.
CP and bytes outside AP are preserved from v38; verify CRC and partial slice
using verify_bk7258_linear_crc_image.py before flashing.

Partial SHA256: 92bb422ca8ecd455a1258aed38b2553cf618c7ab9600647767978f5072de3565
Windows copy: C:/Users/yang/Desktop/openvela/openvela-cp-ap-update-v39-rtc-probe-at-0x11000.bin

At CP `$`, enter `ap_console open`. At `nsh>`:

```text
rtsa_probe status
rtsa_probe init f458b56136964d83acc1053c3b133cd0
```

Wait for checkpoint output without issuing more commands. Preserve the full
output including any reset. Do not repeat init after a failure. If the prompt
remains responsive and no reboot occurs after 10 seconds, collect:

```text
rtsa_probe status
xiaopai ipc status
ps
```

SDK step codes: 1=preflight, 2=init, 3=create, 4=destroy, 5=fini.
The checkpoint preceding a failure narrows the search but is not itself a
backtrace; asynchronous workers may also be active. A successful run requires
done/result=0 plus continued heartbeat acknowledgments, not just launch success.
