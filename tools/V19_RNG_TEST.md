# V19 CP Random Service Prerequisite

Status: CP/AP builds and host tests passed. User hardware logs confirm repeated
RNG checks before and after association, DHCP, and repeated HTTP 200 responses
(559 bytes, exit 0). Uptime reached 50:23 with an intervening hotspot outage;
this is not 50 minutes of continuous network testing. Hotspot recovery failed:
CP state 2, empty SSID, old AP IPv4 retained. V20 addresses runtime reconnect.
This is not an HTTPS implementation. V18 plain HTTP passed twice on hardware.

## Artifact

Ubuntu image:
`/home/yang/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v19.bin`

- Size: 8388608 bytes.
- SHA256: `537458e6051a8f4d2e9fb7d1f0097330286472aaeb62d0c285ae2c55126fc7b8`.
- CP raw: 992216 bytes; encoded: 1054238 bytes.
- AP raw: 394560 bytes; encoded: 419220 bytes; static RAM: 158560 bytes.
- Both CP and AP changed. Do not combine the new AP with an older CP.
- Base is v18; bootloader and bytes outside CP/AP are preserved.
- Original CP sources are saved as `bk7258_package/v19-before.tar`.

Raw CP SHA256:
`05e273dee83d9547ce1eeacc88035faeab862a909deaf4d0547aad39699b6f52`.
Raw AP SHA256:
`03c8a3722bf1b3dfd8b1436e5f9a3b436e5f66e35d53ee3859082dec36a9a0b4`.

## Changes And Limits

CP owns TRNG hardware. Command 0x213 accepts no payload and returns 40 bytes:
signed status, ABI version 1, and 32 random bytes. The AP validates all fields.
CP start/warm-up/discard/read/stop is serialized with the SDK critical section;
large CP requests use at most 32 bytes per critical section. Vendor warm-up
and discarded samples are preserved. No AP direct TRNG register access.

AP `/dev/random` reads at most 32 bytes per call. Callers must handle short
reads. Constant/repeated blocks latch an error until reboot. Transport errors
return errors without exposing data. There is no software random fallback.
`xiaopai rngcheck` reads 256 bytes, checks eight distinct blocks, then erases
samples without printing them. This checks transport/stuck output only, not
entropy quality or cryptographic certification.

NSH `date` is enabled; hardware reported January 1, 1970. There is no verified
RTC or time synchronization.
Boot calendar time must not be trusted for certificate validation. TLS still
needs a short-read-safe entropy adapter, trusted time, CA validation, hostname
validation, bounded I/O and negative certificate tests. Do not disable TLS
verification to work around those prerequisites.

## Reproduction

`v19-cp-trng.patch` is incremental against the existing v17 CP modifications,
not a complete patch against the vendor SDK. From the matching SDK root:

```sh
git apply --check --ignore-space-change /path/to/v19-cp-trng.patch
git apply --ignore-space-change /path/to/v19-cp-trng.patch
```

Mixed vendor line endings require `--ignore-space-change`. A reverse check
against the built SDK passed; plain `patch` rejects its mixed line endings.

Host tests use the actual source with hardware/transport stubs and UBSan:

```sh
python3 test_cp_random.py CP_TRNG_DRIVER AP_RANDOM_DRIVER
python3 test_cp_random_protocol.py CP_CIF_CNTRL AP_WIFI
python3 test_httpcheck.py APPS_DIR XIAOPAI_APP_DIR
python3 test_linear_crc_image.py
python3 verify_bk7258_linear_crc_image.py --base V18 --cp CP_RAW --ap AP_RAW --image V19
```

Covered: init failure, warm-up/discard sequence, full-width words, chunk
bound, tail writes, IRQ restoration, short reads, transport errors, stuck
output, invalid request/response size/version/status. All passed. The 14 HTTP
regression cases and four packager cases also passed. These do not substitute
for board tests or measure real IRQ latency.

## User-Operated Hardware Test

Close miniterm with Ctrl+] before flashing. Run in Ubuntu:

```sh
cd ~/桌面/BEKEN_BKFIL_V2.1.11.8_20240509
./bk_loader download -p 0 -b 1500000 -g 60 -s 0x0 \
  -i ~/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v19.bin
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

The user handles downloading and RST. If an agent requests RST, it must wait
for confirmation before continuing dependent work. No reset is needed for
the commands below. In the board CP console, enter `ap_console open`, then:

```text
xiaopai rngcheck
echo $?
xiaopai rngcheck
echo $?
date
uptime
```

Expect `RNG check v19 passed` and return 0 twice. RNG should work before
joining Wi-Fi. Then connect using the v18 instructions with interface
`xiaopai`, obtain DHCP and repeat `rngcheck` plus `xiaopai httpcheck` twice.
Do not paste Wi-Fi credentials into shared logs. Check uptime after at least
ten minutes for unexpected resets. If RNG fails, retain the error; do not
keep resetting to conceal a latched failure. Do not push until verified.
