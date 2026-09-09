# Continuous PCM Transport

## Scope

Update: the v27 voice worker now calls this core. See [VOICE_V27.md](VOICE_V27.md)
for the application integration, 24 kHz TTS option and current validation scope.
The description below records the original core-only milestone.

`CONFIG_BK7258_PCM` adds a task-callable, half-duplex PCM transport in
`nuttx/arch/arm/src/bk7258/bk7258_pcm.c`, declared in `include/bk7258_pcm.h`.
It uses the existing internal ADC/DAC driver, not I2S, with the existing
16 kHz / signed 16-bit / mono configuration. No chip gain or clock parameter
is changed. Capture keeps the already-tested ADC FIFO threshold 4.

This is the buffering layer for the next application/voice-worker integration.
It is not yet a NuttX audio lower-half, does not register `/dev/audio`, and is
not invoked by the current XiaoPai commands or at boot. Enabling its build
option compiles it into libarch; the linker may discard it until a caller is
linked. Existing diagnostic commands remain separate. No new flash image is
required for this source milestone, and no microphone, speaker or cloud
request is started automatically.

The reference board lower-half was inspected, but not imported wholesale:
its reservation/cancellation and background callback lifetime handling needs
adaptation to this tree's upper-half. In particular, current `audio_close`
calls shutdown with the upper spinlock held. Callback synchronization cannot
simply wait on that lock during close. That integration remains separate.

## API Contract

- `bk7258_pcm_start(capture, &session)` explicitly acquires the hardware and
  starts one direction. It rejects another stream or active diagnostic with
  `-EBUSY`. The opaque nonzero session token must be passed to later calls.
- `bk7258_pcm_read` and `bk7258_pcm_write` return a sample count, not bytes.
  Calls move at most 320 samples (20 ms). Partial transfers are normal;
  callers advance by the returned count. Empty/full returns `-EAGAIN`; no
  data wait is performed. Task-control mutexes can briefly serialize calls.
- The 4096-sample ring is 8192 bytes / 256 ms. A consumer must service it
  regularly. There is no artificial one-second duration limit.
- Capture discards the initial 3200 settling samples, then stores raw MIC1
  samples. When full, newly read samples are dropped and counted explicitly.
  Already queued samples remain in order. A cloud worker must treat a changed
  drop count as a discontinuity, not silently claim uninterrupted audio.
- Playback preserves the initial safety policy: divide PCM by four, clamp
  to +/-1024 and apply a 160-sample startup ramp. This is not bit-exact
  playback or a production volume policy. It does not claim to solve the
  operator's low-volume/noise observations. Underruns send zeros and count
  those samples, avoiding repeated stale samples.
- `bk7258_pcm_drain(session, timeout_ms)` accepts 1..2000 ms, stops inserting
  silence and waits for the ring and hardware FIFO to empty. It serializes
  task calls; no new writes are accepted after drain begins. Even after a
  timeout or interruption, the caller must stop the session.
- `bk7258_pcm_stop` masks IRQs, detaches callbacks, disables the PA and ADC/DAC,
  wipes the ring and releases ownership. A stopped session becomes invalid.
  Always call it on normal completion, cancellation and error. This layer
  does not automatically clean up a caller killed without running cleanup.
- `bk7258_pcm_status` snapshots state/counters with interrupts protected.
  FIFO boundary observations are separate from software-dropped samples.
  Four consecutive no-progress callbacks mask IRQs, stop the digital paths
  and shut down the PA. Task-side stop still completes analog cleanup.

The first client should be a cancellable voice worker that consumes capture
frames and queues decoded playback frames. Half-duplex ownership means the
worker must stop capture before starting playback. Full-duplex/AEC, codecs,
voice activity detection, ASR/TTS and cloud voice transport are not supplied
by this layer. The existing MiMo text client is not a voice client.

## Software Checks

```sh
cd /home/yang/openvela
python3 contest2026_470_huanledoudizhu/tools/test_pcm_stream.py nuttx/arch/arm/src/bk7258
python3 contest2026_470_huanledoudizhu/tools/test_audio_diag.py nuttx/arch/arm/src/bk7258
python3 contest2026_470_huanledoudizhu/tools/test_audio_registers.py nuttx/arch/arm/src/bk7258
. build/envsetup.sh
cmake --build cmake_out/configs_nsh --target resetconfig
cmake --build cmake_out/configs_nsh -j8
```

Tests compile the actual controller with ASan/UBSan and fake FIFO/time.
They exercise six seconds of continuous simulated capture and playback,
ring wrap, partial I/O, overflow/drop accounting, underrun silence, signed
ramping/limiting, drain deadlines, stale tokens, ownership and error cleanup.
The chip-driver test covers real ownership code with fake MMIO/PWC. These
are software checks, not new hardware timing or sound-quality validation.
Per the operator's request, no additional board audio tests are requested.

Remote source backup: `bk7258_package/pcm-stream-before.tar`.
Configuration/build logs: `bk7258_package/pcm-stream-config.log` and
`bk7258_package/pcm-stream-build.log`.

The three software suites and full AP build passed. A final incremental build
also passed (`pcm-stream-build-final.log`). The full build retains existing
unused-variable warnings in startup/PWC, mbedTLS preprocessor warnings and the
discarded linker build-id warning; no warning was reported for the PCM source.
The PCM object was compiled into libarch with `CONFIG_BK7258_PCM=y`; no current
application references it yet, so the linked image does not include its ring.
