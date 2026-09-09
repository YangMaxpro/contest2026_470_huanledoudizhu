# v42 preserve later cleanup diagnostics

v41 observed thread 31 enter pthread_exit and thread 30 return successfully
from __mpq_destroy_wait. Later frees reached ap_selector_destroy,
dns_session_destroy and argus_selector_destroy. All recorded free/close
pairs returned. The 128-line limit was reached before AP heartbeat loss,
so the final printed free must not be treated as the faulting operation.

Addresses were mapped with nuttx-v41-rtc-probe.elf:
- 0x021e217a: __mpq_destroy_wait, mpq.c:1918
- 0x021deaf0: k_os_thread_entry, thread.c:72
- 0x021b997a: ap_selector_destroy, ap_server.c:492
- 0x021c0828: dns_session_destroy, rtc_service_dns.c:52
- 0x021d96f4: argus_selector_destroy, argus_server.c:445

v42 removes free-end lines (void return) and raises the cap to 512. A free
begin alone does not prove completion; subsequent activity from the same
thread is needed. Other operation pairs, error behavior, priorities and
heartbeat timeout remain unchanged. Timing remains affected by diagnostics.
The root cause is not yet fixed or proven.

Worker/trace tests and ARM GCC build passed. Raw AP 1,073,472 bytes,
encoded 1,140,564; static RAM 175,440. No cloud calls or auto flashing.

## Flash

Quit miniterm, then run in the Ubuntu loader directory:

```sh
./bk_loader download -p 0 -b 1500000 -s 0x11000 \
  -i /home/yang/openvela/bk7258_package/openvela-cp-ap-update-v42-rtc-probe-at-0x11000.bin
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

Do not chip erase or flash this partial image at zero. Use established
download/reset procedure; cold power-cycle and confirm PSRAM ready.
Partial range [0x11000,0x286000), 2,576,384 bytes.
SHA256: 8be1de491f1d132aa6fa5e0e1a608b9003ba3ded41cc6b19f1b964cf58c27e87
Matching ELF: /home/yang/openvela/bk7258_package/nuttx-v42-rtc-probe.elf

At CP `$`, run `ap_console open`. At `nsh>`:

```text
rtsa_probe status
rtsa_probe init f458b56136964d83acc1053c3b133cd0
```

Capture all logs for at least 30 seconds, including any reset. Do not repeat
init. If still responsive, collect probe status, IPC status and ps. No key,
token, channel join or audio capture is needed.
