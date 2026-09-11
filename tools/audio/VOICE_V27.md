# XiaoPai Direct MiMo Voice (v27)

## Implemented Scope

An explicit, single-turn, half-duplex workflow runs on an independent NuttX
task: microphone -> MiMo ASR -> selected MiMo text model -> MiMo TTS -> DAC.
No self-hosted server, automatic recording, cloud request at boot, wake word,
voice cloning, persistent recording or conversation history is enabled.
Replies are spoken text only; model output is never executed as a command.

Official interfaces checked on 2026-09-07:

- ASR: https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/Speech-Recognition
- TTS: https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5

Both use `https://api.xiaomimimo.com/v1/chat/completions` with `api-key`.
ASR uses `mimo-v2.5-asr`, `input_audio.data` as WAV/data-URL/base64 and
`asr_options.language=auto`. Text uses the existing configured model.
TTS uses `mimo-v2.5-tts`, target text in an `assistant` message,
`audio.format=pcm16`, `audio.voice=mimo_default`, and `stream=true`.
The documented TTS stream is 24 kHz signed-16 little-endian mono.

## Credentials

The firmware accepts both normal pay-as-you-go `sk-` keys and the Token Plan
`tp-` keys shown by the Xiaomi console. `sk-` uses the public API endpoint;
`tp-` selects the Token Plan China-compatible OpenAI endpoint shown in the
console (`token-plan-cn.xiaomimimo.com`). Follow the terms and usage limits
attached to the account. A model appearing in an entitlement list does not
remove those restrictions.

Never paste a real key into chat, a command argument, source, logs or a build
script. Revoke/reset any key that was disclosed. `cloud key` reads hidden
interactive input directly, outside NSH command history. Disable the terminal's
local echo. The key lives only in RAM and is wiped by `cloud clear` or reboot.
An active voice turn owns the MiMo client; stop and wait for it before clearing
or changing credentials. The firmware image contains no key or Wi-Fi password.

## Operator Workflow

After installing the application firmware, enter `ap_console open` at the CP
`$` prompt. All subsequent commands are entered at `nsh>`.

First connect the `xiaopai` interface using the existing `ifup`/`wapi` workflow
and start `xiaopai netwatch start` for DHCP. Do not run `renew` concurrently
with netwatch. Set accurate current UTC with `date -u -s`; do not copy an old
example date. Certificate verification stays mandatory.

```text
xiaopai cloud key
xiaopai cloud status
xiaopai voice start 3
xiaopai voice status
```

`cloud key` then prompts for the key. `voice start 3` authorizes one three-second
recording and ASR/model/TTS requests, which can consume account quota. Wait for
`recording/uploading to Xiaomi; speak now` before speaking. TLS connection setup
happens before the microphone is opened. There is the existing 200 ms ADC
settling period; speak a short phrase after the prompt. Keep the speaker away
from ears. Use `voice start 5` for a longer phrase; supported range is 1..10 s.

`voice start` launches a task and returns immediately. Its shell exit code
only reports successful launch, NOT a completed conversation. Completion is
`voice: complete result=0`, or `voice status` with `running=0 result=0` and an
incremented completed count. Recognized text and the model reply are printed
with terminal controls filtered. Serial logs can therefore contain conversation
text even though audio is not saved.

```text
xiaopai voice stop
xiaopai voice status
xiaopai cloud clear
```

Wait for `running=0` before `cloud clear`. Do not forcibly kill the worker.
Stop is cooperative; socket polling checks at most every 100 ms, but system DNS
resolution, hardware setup and final DAC drain can delay it. Already uploaded
audio or already played speech cannot be recalled. Cancellation cannot guarantee
that a remote request was not billed. There are no automatic retries.

## Resource and Audio Policy

- ASR generates WAV and base64 incrementally, without a full clip allocation.
  The existing 8 KiB PCM ring holds 256 ms at 16 kHz. If uplink backpressure
  overruns it, the request aborts with `-EOVERFLOW` rather than accepting a
  discontinuous recording. This must be assessed on the actual network.
- ASR response is bounded to 8 KiB; transcript to 512 UTF-8 bytes; model reply
  to 2048 bytes. An oversized response is rejected, never silently truncated.
- TTS uses bounded SSE events (32 KiB), cJSON with depth/node guards, incremental
  base64 decoding, partial PCM writes, and explicit end-of-stream validation.
  Total response is capped at 4 MiB and spoken PCM at 45 seconds. An endpoint
  emitting larger individual chunks is rejected; no PSRAM allocator is assumed.
- Each HTTPS stage has a 60-second socket deadline, including processing and
  playback for TTS. DNS uses the system resolver timeout. Certificate, hostname,
  and validity-date checks are never bypassed; redirects are rejected.
- Capture remains 16 kHz with unchanged analog/digital microphone gains.
  TTS selects the existing vendor 24 kHz DAC divider through `start_rate`.
  Legacy `bk7258_pcm_start` remains 16 kHz. No software resampling is used.
- TTS PCM is attenuated by eight before the core's existing divide-by-four,
  giving an overall 1/32 gain and preserving the +/-1024 safety limit without
  routine clipping of full-scale cloud audio. This is conservative prototype
  volume, not a final loudness/quality solution.
- Playback gaps insert zeros and are counted, not replayed as stale audio.
  No full-duplex echo cancellation, barge-in, VAD or hands-free wake word is
  claimed. The audio core is not a `/dev/audio` lower-half.

## Verification

No real credential, microphone recording or paid cloud invocation was used in
software verification. Tests use synthetic PCM and local fake cloud responses.

```sh
cd /home/yang/openvela
python3 contest2026_470_huanledoudizhu/tools/audio/test_voice.py apps contest2026_470_huanledoudizhu/app/xiaopai nuttx/arch/arm/src/bk7258
python3 contest2026_470_huanledoudizhu/tools/audio/test_pcm_stream.py nuttx/arch/arm/src/bk7258
python3 contest2026_470_huanledoudizhu/tools/audio/test_audio_diag.py nuttx/arch/arm/src/bk7258
python3 contest2026_470_huanledoudizhu/tools/audio/test_audio_registers.py nuttx/arch/arm/src/bk7258
python3 contest2026_470_huanledoudizhu/tools/network/test_mimo.py apps contest2026_470_huanledoudizhu/app/xiaopai
. build/envsetup.sh
python3 contest2026_470_huanledoudizhu/tools/network/test_httpscheck.py apps contest2026_470_huanledoudizhu/app/xiaopai cmake_out/configs_nsh/.config --mimo --stream
cmake --build cmake_out/configs_nsh -j8
```

Voice tests compile the real C worker with ASan/UBSan and fake hardware/cloud.
They check source framing down to WAV sample bytes, partial input/output,
the three request schemas, split/multiline SSE, malformed/truncated data,
overrun, cancellation, task creation and I/O failures, and ownership cleanup.
TLS tests use real mbedTLS/webclient against generated localhost certificates,
including streaming uploads/responses, caps, cancellation, invalid callbacks,
auth failures, certificate/date failures, redirects and descriptor cleanup.
MMIO tests cover selection of 24 kHz DAC and restoration to 16 kHz.

This is software/build validation, not a hardware cloud-voice acceptance result.
Actual API chunk sizes, latency, network backpressure, heap headroom, 24 kHz
playback timing and intelligibility remain unverified on the board. No additional
standalone microphone/noise tests are requested. Full hands-free/product behavior
is outside this single-turn milestone.
