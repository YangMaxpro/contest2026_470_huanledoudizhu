# RTSA OpenVela port (experimental, disabled in baseline)

Target: vendor RTSA 1.9.5.7.dbg on BK7258 R1, retaining OpenVela.
No credentials are stored here. No live RTC or ConvoAI session has been run.

## Implemented

`rtsa_sync.c` translates the vendor pthread synchronization boundary into
native pthread objects. Vendor storage carries a heap-object handle via memcpy;
it is not cast to OpenVela structures. Mutex types are translated explicitly.
Vendor DWARF reports mutex storage 100 bytes and condition storage 96 bytes.
Timed waits and clock_gettime use the DWARF-verified int64 seconds plus int32
nanoseconds layout.

Host ASan/UBSan tests cover recursion, cross-thread condition signaling,
timeout, destruction, unaligned storage and surrounding guards. The shim
also compiles with the actual OpenVela headers and Cortex-M33 hard-float tools.
This does not establish complete SDK runtime compatibility.

The replaced vendor `k_lock_lock` retains its fail-stop behavior. A lock
failure logs the vendor storage slot, the native handle used for the attempted
lock, the native pthread error and the immediate SDK caller before aborting.
It never retries, ignores the error or recreates a lock.

## Integration constraints

- Rename only vendor archive imports to `rtsa_pthread_*`; do not globally wrap
  pthread symbols, which would affect NuttX and recurse into the shim itself.
- Objects require explicit initialization. Concurrent init/destroy and use
  after destroy are unsupported, consistent with POSIX lifetime requirements.
- IPv4, select, basic socket options, thread, allocator and clock shims now
  exist and compile against the current OpenVela headers. None is enabled
  in the default firmware. Unsupported network options fail explicitly.
- Audit sockaddr/addrinfo/fd_set/options/errno before mapping lwIP sockets.
- Audit vendor task identity/deletion and callback execution contexts.
- Preserve allocator ownership across malloc/free/realloc.
- Check short-enum ABI at every SDK-facing translation unit.
- Full-duplex audio and vendor AEC remain separate unfinished work.

Operational RTC firmware requires native lifecycle and media validation.
The opt-in v37 diagnostic image exists only to perform the local lifecycle
check; it never joins a channel or captures audio. Existing v36 baseline
Wi-Fi/time/heartbeat/audio configuration is unchanged.

## Current verification

- `test_rtsa_sync.py`: ASan/UBSan synchronization, storage and fail-stop
  diagnostic tests.
- `test_rtsa_net.py`: ASan/UBSan local UDP loopback, numeric resolution,
  socket flags/options, select and address boundaries. No public network.
- `test_rtsa_runtime.py`: host time-layout and thread tests (UBSan).
- `test_voice_psram.py`: heap lifecycle, realloc failure and allocation counts.
- `test_rtsa_hal_thread.py`: injected thread-creation failure, context/entry
  preservation and vendor stack-size selection.
- `test_rtsa_libc.py`: EOF and all 256 newlib C-locale ctype entries, IPv4 parsing.
- `test_rtsa_loopback.py`: locked native UDP poll notification and readiness
  checks with a network-boundary mock; not a board backpressure test.
- `link_rtsa_port.py`: compiles seven shim modules for Cortex-M33, renames only
  matching vendor imports, and partially links all three vendor archives.
  47 imports are redirected, and the vendor thread HAL definition is weakened
  so the audited replacement takes precedence. `-D__NuttX__` is explicit:
  previous standalone compilation missed the target scheduling branch.
- `audit_rtsa_native_link.py`: reuses the trusted Ninja link command, adding the
  retained partial object and retaining RTC lifecycle symbols, but redirects
  ELF/map outputs to a temporary directory. Executable ARM linking against the
  existing NuttX libraries now succeeds. This is not an enabled/runnable RTC
  configuration and does not prove initialization or media operation.

## Outstanding integration gates

`rtsa_hal_thread.c` replaces `k_os_thread_create`: the original discards errors,
whereas the replacement returns them to `k_thread_create`, which skips the
startup wait and destroys the handshake on failure. This contract and stack
selection were verified against the 1.9.5.7 disassembly. Preserve the original
context and `k_os_thread_entry`; do not replace the stack-backed handshake.
Re-audit before using any other SDK binary/version.

`rtsa_loopback.c` replaces the vendor's deferred lwIP polling stimulus with
`netdev_txnotify_dev(lo, UDP_POLL)` under the native network lock. NuttX's
loopback driver queues HPWORK to drain pending events. The SDK still owns
its send-failure wakeup counter. Readiness must be checked before SDK init;
actual saturated-queue/event-loop progress still needs native-board testing.

`rtsa_libc.c` supplies a private newlib-compatible C-locale table, IPv4 text
parser and fail-stop assertion adapters. These do not alter native libc.
No constructor/init-array sections were present in the retained SDK object.

The current board configuration also lacks PTHREAD_MUTEX_TYPES and
NET_LOOPBACK, required by the vendor code path. Enable these only in a
separate RTC integration configuration and rerun native-board tests.
Do not start the SDK until PSRAM is ready. SDK initialization is documented
as once per process; do not treat repeated init/fini loops as supported without
further validation. Next gate is explicit, non-cloud init/create/destroy/fini,
then user-authorized channel entry and full-duplex audio.

## v37 diagnostic build

`CONFIG_XIAOPAI_RTSA_PROBE` registers the separate `rtsa_probe` command, never
an automatic boot action. Its worker runs at priority 90 with a 16 KiB stack;
SDK workers run at 100, below the heartbeat at 110. Only the SDK-facing source
uses short enums, with an ABI offset assertion. The command validates the App
ID, checks loopback and PSRAM, and permits only one SDK attempt per boot.
No Token/certificate is required for this local init/create/destroy/fini probe.

`prepare_rtsa_probe_config.py` derives a separate configuration, enabling native
recursive mutexes and loopback while disabling legacy MiMo text/voice to leave
room in the unchanged AP flash partition. Normal Wi-Fi, time, heartbeat and
local audio diagnostics are retained. The v36 build/config are not replaced.

See `tools/V37_RTSA_PROBE.md` in the project root for exact artifacts and steps.
Native execution, channel entry and audio remain unverified until board results
are collected. Host tests cover lifecycle failure cleanup and worker state;
they are not a substitute for those results.
