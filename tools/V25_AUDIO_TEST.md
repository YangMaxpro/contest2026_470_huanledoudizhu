# v25 Bounded Replay Level Test

## Hardware Baseline

The operator's v24 capture: 16000 stored samples, 19209 raw samples in
1200 ms, 2430 IRQs, one full observation, full_after=0, threshold=4.
PCM DC=3, RMS=131, peak=806, clipped=0. Playback returned zero with no
FIFO boundary warning, but the operator heard nothing. A subsequent v24
1 kHz tone was audible (16000 samples, 1100 ms, no boundary warning).
This demonstrates audible output, not intelligible microphone capture.

## One Adjustable Parameter

`xiaopai audio play [8|4|2|1]` selects a software attenuation divisor.
Omitting it preserves v24's divisor 8. Start with 4, only twice the default
PCM amplitude (about +6 dB before limiting), and evaluate before another
change. Divisors 2 and 1 are available for subsequent separately confirmed
tests; do not jump to them or change microphone gain simultaneously.

All levels retain DC subtraction, the +/-1024 peak clamp, 10 ms ramps,
one-second duration, timeout and PA-off cleanup. ADC threshold 4, analog
and digital gains, test tone, capture and CP firmware are unchanged.
No automatic playback, capture, reset, flashing or cloud calls are added.

## Operator Test

The operator flashes on Ubuntu and confirms completion. If RST is needed,
ask explicitly and wait for confirmation. Enter the AP console, record a
short phrase (RAM recordings do not survive flashing), and send the report:

```text
xiaopai audio record
echo $?
```

With the speaker away from ears, run the first level comparison only:

```text
xiaopai audio play 4
echo $?
```

Report whether speech is recognizable, faint, noisy or silent. Stop on
uncomfortable sound. `xiaopai audio play 8` restores the previous level;
the next bare `play` also defaults to 8, so no setting is persisted.
`xiaopai audio clear` wipes the RAM recording. Do not forcibly kill NSH.

Tests exercise the actual controller and CLI with ASan/UBSan, including
all divisors, default behavior, DC subtraction, ramps, clipping bounds,
invalid arguments and existing cleanup/error paths. Register tests ensure
the unchanged ADC threshold and hardware configuration. Simulation cannot
certify sound pressure, captured speech or physical timing.

Image target on Ubuntu:
`/home/yang/openvela/bk7258_package/openvela-correct-linear-crc-8MB-v25.bin`.
Use v24 as packaging base and preserve all bytes outside the AP partition.
Hardware playback at the new levels remains unverified.

## Build Verification

Both host test suites and the incremental AP build passed on Ubuntu.
Only the existing discarded build-id linker warning was emitted.
AP raw size is 675648 bytes; encoded size is 717876 bytes; static RAM is
168080 bytes. The 8388608-byte image was checked against the raw AP, CP v19
and v24 base; CP, bootloader and data outside the AP remain unchanged.

SHA256: `ad860d35c4cc511b95f5d4ca6c43b1f4b9042241fcf153db7cc881de2f382a44`.
Build log: `bk7258_package/v25-ap-build.log` on Ubuntu.
Scoped source backup: `bk7258_package/v25-audio-before.tar`.
