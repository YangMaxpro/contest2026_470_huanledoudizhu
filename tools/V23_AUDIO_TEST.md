# v23 Local Audio Bring-Up

## Scope

Adds `xiaopai audio status|tone|record|play|clear` on AP NSH. No sound or
capture starts automatically. CP remains the v19 binary used by v21.
The existing MiMo text client work is retained but no cloud calls are made.

This is a diagnostic path, not yet a `/dev/audio` streaming driver, voice
assistant, ASR/TTS or acoustic echo cancellation implementation.

## Hardware And Provenance

- Internal analog MIC1 ADC, 16 kHz, signed 16-bit mono.
- Internal differential DAC, AUDLP/AUDLN -> external amplifier -> CN8.
- GPIO50, high enables amplifier, low shuts it down (R70/R71/CTRL).
- Board schematic overview says HT6872; the detailed sheet labels HT6873.
- MIC2 is reserved for the schematic echo-reference path; not used here.
- Chip register definitions and sequences adapted from the existing
  `ref264/board/beken/chips/bk7258` reference with its Apache-2.0 notices.
  Its historical measurement comments are NOT verification of this build.
- AP services the FIFO; CP still owns audio power/clock votes via PWC.
  The AP does not override CP's shared clock selector or module-clock gate.

## Limits And Cleanup

- Tone: one second, 1 kHz, peak 320/32768, 10 ms ramps.
- Capture: discard first 200 ms, then store one second (32000 bytes) in RAM.
- Replay is a separate command: subtract capture DC, divide by eight,
  clamp to +/-1024 and ramp both ends. No automatic gain normalization.
- Report raw DC, RMS, peak, clipping and FIFO fault counters.
- ISR work is bounded to 64 samples; repeated no-progress IRQs are masked.
- Three-second monotonic transfer timeout, cooperative signal cancellation,
  mutually exclusive operations. Cleanup disables PA and FIFO interrupts,
  removes callbacks and shuts down ADC/DAC. Do not forcibly kill NSH during
  a test; SIGKILL does not run cleanup.
- Failed captures are zeroed and cannot be replayed. `clear` wipes/frees RAM.
- `status` displays the last test, not a claim of working physical audio.

## Build And Host Tests (Ubuntu)

From `/home/yang/openvela`:

```sh
. build/envsetup.sh
cmake --build cmake_out/configs_nsh --target resetconfig
cmake --build cmake_out/configs_nsh -j8
python3 contest2026_470_huanledoudizhu/tools/test_audio_diag.py nuttx/arch/arm/src/bk7258
python3 contest2026_470_huanledoudizhu/tools/test_audio_registers.py nuttx/arch/arm/src/bk7258
```

The tests compile actual controller/driver C with hardware stubs. They cover
sample bounds, settling, statistics, replay, clearing, mutex exclusion,
allocation/setup errors, timeout, stalled IRQ, interruption, PWC sequencing,
FIFO word packing and partial-setup cleanup. They cannot prove acoustics or
real hardware timing.

## Hardware Verification (Operator Only)

Built artifact on Ubuntu:
`/home/yang/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v23.bin`

- Image size: 8388608 bytes.
- SHA256: `f7bbd4988786d6ee146c033665c7d18a7457a2a0109e001e540b334a47658e9f`.
- AP raw: 674624 bytes; CRC-encoded: 716788 bytes; static RAM: 168000 bytes.
- CP v19, bootloader and all bytes outside the AP partition preserved from v21.
- Both host test suites and Ubuntu target build passed. Hardware testing pending.

Flash the new v23 image in Ubuntu with the existing loader procedure.
Do not restore the factory backup. No automated flashing or RST is performed.
When RST is needed, wait for the operator's confirmation before continuing.

Open serial, then at the CP `$` prompt:

```text
ap_console open
```

At `nsh>`, keep the speaker away from ears. First run only:

```text
xiaopai audio status
xiaopai audio tone
echo $?
```

Check for a brief, quiet tone and return value zero. Send the full output.
If it is silent, noisy, or times out, stop and inspect before more tests.

After tone verification, run `xiaopai audio record` and speak immediately
for one second. Inspect counts (16000), RMS/peak and clipping, then explicitly
run `xiaopai audio play`. Repeat with a quiet-room capture for comparison.
Run `xiaopai audio clear` when finished. Hearing recognizable speech is
required; nonzero samples alone do not prove a working microphone.

Finally repeat Wi-Fi/DHCP/HTTPS and `uptime` checks to detect regressions.
The netwatch/time setup requirements remain unchanged from v21.
