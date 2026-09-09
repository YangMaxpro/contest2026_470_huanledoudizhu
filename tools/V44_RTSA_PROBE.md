# v44 lock-failure capture

The SDK now reaches the replacement for `k_lock_lock` before aborting. This
is a fail-stop boundary: a failed lock can result from an invalid or destroyed
lock, an unsupported caller context, recursive use of a non-recursive lock or
another native pthread error. It is not safe to ignore the error or construct
a replacement lock at that point.

v44 preserves the vendor abort and adds one line immediately before it:

```text
RTSA lock failure: slot=<vendor-storage> handle=<native-mutex> error=<pthread-result> caller=<SDK-return-address>
```

`slot` identifies the SDK lock storage; `handle` is the exact native mutex
passed to `pthread_mutex_lock`; `error` is the unmodified native return code;
and `caller` is the instruction in the SDK immediately above the generic lock
wrapper. The caller must be symbolized against the matching v44 ELF before
assigning a source-level cause. A null handle with `error=22` means the shim
observed no initialized handle in that storage; it does not prove why the SDK
used it.

Host ASan/UBSan coverage now launches a deliberate uninitialized-slot call in
a child process and verifies the four fields plus `SIGABRT`. This validates
the diagnostic contract, not an SDK runtime fix. Board execution, channel
entry, media capture and automatic flashing remain out of scope.
