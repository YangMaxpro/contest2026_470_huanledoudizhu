# v43 AHPL TLS cleanup use-after-free fix

## Evidence

v42 cleanup reaches __rb_walk_func (tls.c:317/323). Last frees include
0x2803ed88 (SRAM passed to the PSRAM-only free wrapper) and 0x6072015c
(not a valid aligned user allocation), followed by AP loss and CP reset.

In archived v42 ELF, __rb_traverse_ldr calls its visitor at 0x021e81e0,
then loads the current node's right pointer at 0x021e81e6. The TLS visitor
__rb_walk_func frees that node at 0x021e8a24. Thus the walker dereferences
freed storage, whose contents can be overwritten by the NuttX allocator.
This is a concrete defect consistent with the invalid frees in the log.
It does not establish that every possible remaining board fault is fixed.

## Fix and verification

Replace only AHPL's public in-order walker with a compatible implementation
that snapshots left/right children before visiting/freeing the current node.
Preserve in-order callbacks and early-stop behavior. The original archive is
not edited; its symbol is weakened in the private intermediate object.
Final ARM disassembly confirms rb_tls_deinit calls the replacement.

Host ASan/UBSan test reproduces heap-use-after-free using the old instruction
order; the replacement passes freeing callbacks, empty trees and early stop.
Full isolated ARM build passed: raw AP 1,073,984 bytes, encoded 1,141,108,
static RAM 175,440. Prior diagnostics remain enabled for board validation.
No channel join, recording, cloud calls or automatic flashing performed.

## Flash and validate

Exit miniterm. In Ubuntu:

```sh
cd ~/桌面/BEKEN_BKFIL_V2.1.11.8_20240509
./bk_loader download -p 0 -b 1500000 -s 0x11000 \
  -i /home/yang/openvela/bk7258_package/openvela-cp-ap-update-v43-rtc-probe-at-0x11000.bin
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

Do not chip-erase or write the partial image at zero. Cold power-cycle after
flashing and confirm PSRAM ready. At CP `$`, run `ap_console open`, then:

```text
rtsa_probe status
rtsa_probe init f458b56136964d83acc1053c3b133cd0
```

Wait for cleanup to finish, then collect:

```text
rtsa_probe status
xiaopai ipc status
free
```

Required result: done, running=0, result=0, callback_error=0, heartbeat
continues and no reboot. Review before/after heap bytes rather than assuming
memory cleanup passed. Do not run init twice in one boot.

Partial range [0x11000,0x286000), 2,576,384 bytes.
SHA256: d5a1dbd372281e6058997648224b5a6734f651eb4b28395808935644aed14a21
Matching ELF: /home/yang/openvela/bk7258_package/nuttx-v43-rtc-probe.elf
CP/boot/data preserved against v42; CRC and exact partial slice verified.
