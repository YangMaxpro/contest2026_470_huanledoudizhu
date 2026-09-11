# V32 Boot NSH Stack

## Evidence

On v31, direct `ps` stopped after PID 9 (`bk-wifi`), then CP reset the system
after an 8000 ms heartbeat gap. Before `ps`, attempts and ACKs matched and the
mailbox had no timeouts or bad ACKs. Removing heartbeat console writes in v31
did not fix this reproduction.

On the same firmware the user ran `nsh -c "ps"`. It completed and returned to
the prompt, showing both PID 10 `nsh_main` (adjusted stack 2000 bytes) and PID
11 `nsh -c ps` (adjusted stack 4040 bytes).

The code explains the allocation difference: `nx_start_application()` in
`nuttx/sched/init/nx_bringup.c` assigns `CONFIG_INIT_STACKSIZE` to the initial
task. It enters `nsh_main` and `nsh_session` directly. The builtin table uses
`CONFIG_SYSTEM_NSH_STACKSIZE` for separately launched shells. The existing
4096-byte SYSTEM_NSH setting did not enlarge the boot shell's 2048-byte stack.

This comparison strongly implicates boot-shell stack headroom, but also changes
execution context; it is not a captured overflow fault or a long-term stability
proof. Compiler per-function stack reports alone do not prove runtime overflow.

## Change

Only the BK7258 NSH defconfig changes:

- `CONFIG_INIT_STACKSIZE=4096`, matching the already tested builtin NSH.
- `CONFIG_STACK_COLORATION=y`, using the existing ARM stack initialization and
  high-water APIs so `ps` shows STACK/USED/FILLED. No stack-monitor task is added.

The boot task uses 2048 additional heap bytes. High-water measurements are
approximate observations, not overflow protection. Heartbeat interval, priority,
timeout and CP firmware remain unchanged. The IPC banner still says v31 because
that service has not changed. Networking persistence/autostart is not included.

## Verification

The generated config must show INIT_STACKSIZE=4096, SYSTEM_NSH_STACKSIZE=4096,
and STACK_COLORATION=y. Relative to the v31 generated config, only those two
active options change (new disabled options are Kconfig visibility effects).

```sh
python3 contest2026_470_huanledoudizhu/tools/system/test_heartbeat.py nuttx/arch/arm/src/bk7258
cmake --build cmake_out/configs_nsh -j8
```

The heartbeat host regression, full firmware build and image CRC verification
passed. The build still reports the existing mbedTLS undefined-macro warning
and discarded build-id warning. Hardware acceptance of v32 is pending.
The image preserves the v31 CP, bootloader and bytes outside firmware partitions.

Image on Ubuntu:
`/home/yang/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v32.bin`

Size: 8388608 bytes; raw AP: 694080 bytes; encoded AP: 737460 bytes.
SHA256: `4110911768b218a2d39936a6e9bd92d9d7cf80bbae6613b4c0c6895d38c16dfe`

Configuration backup on Ubuntu:
`/home/yang/openvela/bk7258_package/nsh-v32-iDIldr/before.tar.gz`.
The board has not been flashed by the agent. The full-image loader workflow
may replace stored board data with data from the base image.

After manually flashing v32, enter AP console once and execute plain `ps`
without launching a second shell. Wait for its prompt before the next command:

```text
ps
xiaopai ipc status
sleep 10
xiaopai ipc status
```

Expect the boot `nsh_main` STACK to be about 4 KiB, with USED/FILLED columns,
the full task list, and advancing heartbeat ACKs without new failures. Stop on
any link-down/reset and retain the log. No Wi-Fi setup, key or cloud request is
needed for this check. Success here does not yet establish cloud-load stability.
