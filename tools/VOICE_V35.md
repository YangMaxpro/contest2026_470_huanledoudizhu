# Voice v35: bounded capture before upload

The ASR body source previously drained the 4096-sample PCM ring while TLS
sent the request. A blocked network write could overrun that 256 ms ring.

The source now records the complete requested 1..10 seconds after verified
TLS, stops capture, and only then supplies WAV/base64 to the HTTP writer.
The recording occupies 32,000..320,000 bytes in a dedicated AP PSRAM heap
(0x60720000..0x60a00000), not the SRAM system heap. The existing CP PWC
power acknowledgement gates allocator initialization. The MPU mapping is
non-cacheable. CP heap, media pools and linker PSRAM sections are untouched.
The allocator refuses shutdown while allocations remain outstanding.

Cancellation/deadline and PCM overrun checks remain active during capture.
All normal success/error exits wipe and release the recording. No retries,
persistent recordings, automatic capture, gain or audio register changes.
The existing 60 second request budget still includes capture and upload.

## Verification

- AP build passed; raw AP 705856 bytes, encoded 749972 bytes.
- Voice host ASan/UBSan: complete WAV/base64 data at 1, 3, 10 seconds;
  partial reads, delayed upload with microphone stopped, cancellation,
  allocation/read/overrun failures, SSE parsing and cleanup.
- Dedicated PSRAM allocator host simulation passed lifecycle and busy shutdown.
- Existing PCM simulation passed.
- Full image CRC and unchanged bytes outside CP/AP verified; CP unchanged.
- No board flashing or paid cloud requests performed. PSRAM access on the
  board and real ASR/model/TTS completion still require hardware validation.

## Upgrade

Close miniterm first. On Ubuntu:

```sh
cd ~/桌面/BEKEN_BKFIL_V2.1.11.8_20240509
./bk_loader download -p 0 -b 1500000 -s 0x11000 -i /home/yang/openvela/bk7258_package/openvela-cp-ap-update-v35-at-0x11000.bin
```

Use the usual hardware download/reset procedure. Do not use chip erase or
address zero with this partial image. Range: [0x11000, 0x286000), 2576384 bytes.
SHA256: b324e1d33356ff96d9b44bb813395c449dd66387a20624b762ac5b6c1fbd919e

The Wi-Fi profile is preserved. Wait for DHCP/NTP, enter `ap_console open`
from CP `$`, and check `xiaopai voice status` reports v35. Configure a new
API key locally using `xiaopai cloud key` (old disclosed key should be revoked).
Run `xiaopai voice start 3`. Speak only after `recording locally; speak now`.
After the turn, collect `xiaopai voice status` and `xiaopai ipc status`.
If PSRAM initialization fails, collect the complete boot output and do not
continue voice tests. Never include API keys in shared logs.
