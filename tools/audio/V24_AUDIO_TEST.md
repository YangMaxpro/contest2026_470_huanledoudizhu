# v24 ADC FIFO Timing Test

## Baseline And Change

The operator heard the v23 test tone but could not recognize recorded speech.
The reported quiet capture was RMS 72 / peak 553; a speech capture was RMS
267 / peak 1245. Neither clipped. This suggests acoustic response, not proven
speech intelligibility. Capture observed FIFO_FULL on all 1016-1017 IRQs.

Only one hardware parameter changes: ADC FIFO interrupt threshold 16 -> 4.
The vendor register permits 0..31 and requests an IRQ above the threshold.
Earlier servicing should leave more headroom, but FIFO capacity and the
cause of the full observations have not been measured. Hardware verification
is required before calling the problem fixed. v23 retains the old setting.

Following the serial-diagnostic workflow, gain and playback attenuation are
unchanged for this comparison: MIC gain 0, ADC digital gain 0 dB, playback
divided by eight, peak clamped to 1024, one-second clip. No auto recording,
playback, serial parameter writes, flashing, reset or cloud requests.

## New Measurements

- `fifo_faults`: preserves the v23 field for comparison. In capture it counts
  FIFO_FULL observations at ISR entry; in playback it counts mid-transfer
  empty observations. It is NOT an exact lost-sample counter.
- `raw_samples`: samples drained, including the 3200 discarded during startup
  and a possible final partial batch beyond the 16000 stored samples.
- `elapsed_ms`: capture start to final FIFO service, ideally around 1200 ms
  for the settling interval plus one-second clip. Playback measures enqueue
  time, not the final analog output drain.
- `max_batch`: largest number drained/written during one ISR callback.
- `max_irq_gap_ms`: largest tick-measured interval, including start to first
  IRQ. System tick is 10000 us, so this cannot measure sub-millisecond IRQ
  latency. Do NOT interpret a 10 ms result as a proven 10 ms service gap.
- `before_or` / `after_or`: bitwise OR of all FIFO statuses before/after
  service, NOT single simultaneous snapshots. For ADC, full is bit 10,
  empty bit 14, IRQ flag bit 18, matching the vendor register definitions.
- `full_after` / `empty_after`: number of capture callbacks observing each
  flag immediately after draining the FIFO, before copying samples.
- `adc_threshold`: readback from the actual ADC threshold field; expect 4.

The controller still reports transfer completion separately from signal
quality. A FIFO boundary warning does not prove exact loss, and return zero
does not prove recognizable speech. Existing bounded ISR, timeout, PA-off
cleanup and recording erasure behavior are retained.

## Verification

Ubuntu host tests compile actual driver/controller C. ASan/UBSan controller
tests cover new timing/raw/status counters plus the previous bounds, ramps,
settling, replay, wiping, failure, no-progress IRQ and cancellation cases.
Register tests confirm ADC threshold 4, unchanged DAC threshold 16, PWC
ordering, FIFO packing and partial-setup cleanup. Simulation is not hardware.

```sh
cd /home/yang/openvela
python3 contest2026_470_huanledoudizhu/tools/audio/test_audio_diag.py nuttx/arch/arm/src/bk7258
python3 contest2026_470_huanledoudizhu/tools/audio/test_audio_registers.py nuttx/arch/arm/src/bk7258
. build/envsetup.sh
cmake --build cmake_out/configs_nsh -j8
```

The remote backup is `bk7258_package/v24-audio-before.tar`. The v23 image
is retained unchanged. Packaging uses v23 as its base, replacing only AP.

Build and both host test suites passed. The image is on Ubuntu at
`/home/yang/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v24.bin`.

- Size: 8388608 bytes.
- SHA256: `67860528acc0242228304a875f490f7102feb649f39246c4626c60548be978a6`.
- AP: 675648 bytes raw, 717876 bytes encoded; static RAM 168080 bytes.
- CP v19, bootloader and data outside AP verified unchanged from v23.
- Physical capture/voice quality remains unverified for v24.

## Operator Test

The operator flashes in Ubuntu with the existing loader. Wait for confirmation
before proceeding with any requested RST. After entering AP NSH, first run:

```text
xiaopai audio record
echo $?
```

Send all output. Check threshold readback, samples, full observations and
elapsed time before adjusting playback volume or capture gain. If FIFO_FULL
remains on every IRQ, investigate status behavior, IRQ latency and transfer
timing rather than assuming that turning up gain fixes capture.

Keep playback tests separate until capture is assessed. Then verify heartbeat,
Wi-Fi and uptime still behave normally. Do not push changes before board tests.
