# v33: Saved Wi-Fi Profile and Boot Connection

## Scope

- One WPA/WPA2 station profile on interface `xiaopai`: SSID 1..32 bytes,
  password 8..63 printable ASCII bytes. No open network, raw 64-digit PSK,
  enterprise authentication, or multiple-profile roaming in this version.
- `xiaopai wifi save <SSID>` prompts on `/dev/console`, writes the profile,
  reads it back, then requests connection. Password is never an argument.
- `xiaopai wifi connect` loads the saved profile and requests connection.
- `xiaopai wifi status` reports whether a valid profile is stored, without
  printing the SSID/password. Use `netprobe`/`ifconfig` for live link/IP status.
- `xiaopai wifi forget` removes only the stored profile. It does not disconnect
  the active RAM connection or securely erase historical Flash records.
- Boot uses `xiaopai_boot_main`, starts a 4096-byte background worker, then
  calls the normal NSH entry point on the existing 4096-byte boot stack.
  Missing/corrupt profiles never cause a connection. Transport read failures
  get at most three attempts, two seconds apart; NSH remains available.
- Connection uses existing WAPI calls and CP station auto-reconnect. Netwatch
  remains the sole DHCP/DNS owner; its internal ensure operation is idempotent
  and refuses a monitor whose asynchronous stop is still pending.
- No automatic microphone capture, cloud request, cloud-key persistence,
  clock synchronization, or TLS-check bypass is added.

## Storage and Safety

Credentials are PLAINTEXT, not encrypted secure storage. Saving is explicit;
boot/reconnect only reads. An identical saved profile does not cause a write.
The profile is a fixed-size, versioned, canonical blob under the CP EasyFlash
key `xiaopai.wifi.v1`. EasyFlash supplies record CRC, locking and its existing
update/garbage-collection protocol. SET/CLEAR also read back their result.
No raw-sector erasure or factory-reset API is called by this feature.

The current vendor configuration has `CONFIG_FLASH_MB=1` and EasyFlash v4.
CP `flash_lock()` notifies the AP around writes. The active vendor AP
`cpu1_pause_handle()` acknowledges START/END without parking the CPU; it
pauses registered streaming peripherals. The NuttX notification path matches
that active protocol. Both CPUs share Flash; disabled direct-access APIs do
not imply independent physical storage. Future peripheral DMA streaming
requires equivalent pause/resume integration.

Vendor EasyFlash port routines do not consistently propagate low-level Flash
errors. Profile readback detects a mismatching result, but this is not a
claim of power-failure certification or complete Flash failure recovery.
Save/GC under real hardware load and interrupted-power behavior remain to
be validated. Do not interrupt power while saving or forgetting a profile.

## Artifacts

Ubuntu directory: `/home/yang/openvela/bk7258_package/`

Preferred upgrade for a board already running this project's v32 firmware:

`openvela-cp-ap-update-v33-at-0x11000.bin`

- Start address: **0x11000**, not 0.
- Length: 2576384 bytes; exclusive end: 0x286000.
- SHA256: `306c01257b8a76284b41a20a3929d3c338a104a750e10465819a5f95653fa364`
- Exact slice of the verified full image. Covers CP/AP only, preserving the
  device's existing bootloader, configuration and calibration areas.
- Do not enable the loader's `--chip-erase` / `-c` option.

Full recovery image: `openvela-correct-linear-crc-8MB-v33.bin`

- Length: 8388608 bytes, start 0.
- SHA256: `04116045e0c4f06cb421a3e2c4e50736ec70dd36311cf18c042e9931ee7a63b5`
- Based on v32. Its non-firmware bytes match that BASE FILE, not necessarily
  the current board. Full-image flashing can overwrite settings on the board;
  it is not the recommended normal update route.

Raw inputs and logs: `wifi-v33-Q1vSMH/` under the Ubuntu directory above.
CP raw: 992696 bytes; AP raw: 697152 bytes.
Encoded CP: 1054748 bytes; encoded AP: 740724 bytes.
`before.tar.gz` and `config-before` preserve the replaced sources/config.

## Flash and Configure

Quit miniterm with Ctrl+] before flashing. In the Ubuntu terminal:

```sh
cd ~/桌面/BEKEN_BKFIL_V2.1.11.8_20240509
./bk_loader download -p 0 -b 1500000 -s 0x11000 -i /home/yang/openvela/bk7258_package/openvela-cp-ap-update-v33-at-0x11000.bin
```

Follow the board's existing reset/download procedure. After successful
flashing, reboot and open miniterm:

```sh
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

At the CP `$` prompt, enter `ap_console open`. Wait for
`AP console open; exit with Ctrl-], release, then press .` and a live `nsh>`.
Forwarded `ap0: nsh>` output alone does not switch the input console.

With the hotspot on, enter at `nsh>`:

```text
xiaopai wifi save "vivoX300"
```

Turn miniterm local echo OFF. Type the Wi-Fi password only when the hidden
prompt is active, then Enter. Ctrl-C cancels. The prompt times out after
120 seconds. Do not paste the password into the shell or share it in logs.

Wait for `profile saved and read back` followed by `netwatch: DHCP ready`.
Do not run a separate `renew` or manually start a second DHCP client.

## Hardware Acceptance (Pending)

1. Confirm save and DHCP success; inspect `xiaopai ipc status` for failures.
2. Power off/on AFTER saving has completed. With the same hotspot on, do not
   enter `ifup`, `wapi`, `renew`, or `netwatch start`. Expect boot connection
   and DHCP automatically. Then inspect:

   ```text
   xiaopai wifi status
   xiaopai netwatch status
   ifconfig
   xiaopai ipc status
   ```

3. Toggle the hotspot off/on and confirm link/DHCP recovery and healthy IPC.
4. Optional forget test: `xiaopai wifi forget`, reboot, confirm no automatic
   connection. This removes only the profile and leaves other ENV keys alone.

Host tests and builds have passed. No board flashing, reboot, microphone
operation or paid cloud request was performed by the agent. Real persistence
and boot auto-connect are not yet hardware-verified.

## Reproduction

Apply `v33-cp-wifi-profile.patch` to the existing v19-patched CP tree, using
whitespace-tolerant patching for the vendor's mixed line endings. Copy
`cp-v33/xiaopai_wifi_profile_service.h` and
`nuttx/arch/arm/src/bk7258/include/bk7258_wifi_profile.h` into the CP
`components/controller_if/` directory. The latter is the shared wire ABI;
keep the two copies identical. Build `make bk7258_cp` in
`/home/yang/bk7258_sdk/projects/app_ab`.

AP defconfig changes are limited to the init entry/name and
`CONFIG_XIAOPAI_WIFI_PERSIST=y`. Keep `CONFIG_INIT_STACKSIZE=4096`.

Host checks, from the Ubuntu project:

```sh
python3 contest2026_470_huanledoudizhu/tools/network/test_wifi_profile.py /home/yang/openvela
python3 contest2026_470_huanledoudizhu/tools/network/test_netwatch.py contest2026_470_huanledoudizhu/app/xiaopai/xiaopai_netwatch.c
python3 contest2026_470_huanledoudizhu/tools/system/test_heartbeat.py nuttx/arch/arm/src/bk7258
python3 contest2026_470_huanledoudizhu/tools/network/test_wifi_reconnect.py nuttx/arch/arm/src/bk7258
```

These compile production functions with stubbed hardware/time/storage and
undefined-behavior checks. They cover strict ABI, failed/short responses,
corrupt profiles, write/readback failure, deduplication, clear, boot retry
bounds, no-profile startup, console availability, hidden input/cancel/timeout,
configuration serialization, DHCP ownership and existing reconnect/heartbeat
failure cases. They do not simulate the physical Flash/XIP controller.
