/* SPDX-License-Identifier: Apache-2.0 */
#include <nuttx/config.h>
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <nuttx/crc32.h>
#include <arch/chip/bk7258_audio_diag.h>
#include "xiaopai_audio.h"

static int audio_dump(void)
{
  const size_t bytes = BK7258_AUDIO_CLIP_SAMPLES * sizeof(int16_t);
  int16_t *clip = malloc(bytes);
  uint32_t crc = UINT32_MAX;
  unsigned int offset;
  int ret;

  if (clip == NULL) return -ENOMEM;
  ret = bk7258_audio_copy(clip, BK7258_AUDIO_CLIP_SAMPLES);
  if (ret < 0) goto out;
  if (puts("PCM16 BEGIN rate=16000 samples=16000 format=s16le") < 0)
    {
      ret = -EIO;
      goto out;
    }

  /* Snapshot first, then print without holding the audio lock or any IRQ.
   * Explicit LE bytes make the CRC and host WAV independent of host endian. */
  for (offset = 0; offset < BK7258_AUDIO_CLIP_SAMPLES; offset += 32)
    {
      static const char hex[] = "0123456789abcdef";
      uint8_t raw[64];
      char encoded[129];
      unsigned int i;
      for (i = 0; i < 32; i++)
        {
          uint16_t value = (uint16_t)clip[offset + i];
          raw[2 * i] = value & 0xff;
          raw[2 * i + 1] = value >> 8;
        }
      crc = crc32part(raw, sizeof(raw), crc);
      for (i = 0; i < sizeof(raw); i++)
        {
          encoded[2 * i] = hex[raw[i] >> 4];
          encoded[2 * i + 1] = hex[raw[i] & 15];
        }
      encoded[128] = '\0';
      if (printf("PCM16 DATA %05u %s\n", offset, encoded) < 0)
        {
          ret = -EIO;
          goto out;
        }
    }
  ret = printf("PCM16 END crc32=%08" PRIx32 "\n", ~crc) < 0 ? -EIO : 0;
  if (fflush(stdout) != 0) ret = -EIO;
out:
  explicit_bzero(clip, bytes);
  free(clip);
  return ret;
}

int xiaopai_audio(int argc, char *argv[])
{
  static const char *const names[] =
    {"status", "tone", "record", "play", "clear", "silence"};
  struct bk7258_audio_report_s report;
  unsigned int op;
  unsigned int divisor = 8;
  int ret;

  if (argc != 3 && argc != 4) goto usage;
  if (strcmp(argv[2], "dump") == 0)
    {
      if (argc != 3) goto usage;
      ret = audio_dump();
      if (ret == -ENODATA) puts("Audio: no recording; run xiaopai audio record first");
      else if (ret < 0) printf("Audio dump failed: %d\n", ret);
      return ret;
    }
  for (op = 0; op < sizeof(names) / sizeof(names[0]); op++)
    {
      if (strcmp(argv[2], names[op]) == 0) break;
    }
  if (op >= sizeof(names) / sizeof(names[0])) goto usage;
  if (argc == 4)
    {
      if (op != BK7258_AUDIO_PLAY || strlen(argv[3]) != 1 ||
          strchr("8421", argv[3][0]) == NULL) goto usage;
      divisor = argv[3][0] - '0';
    }
  if (op == BK7258_AUDIO_TONE)
    puts("Audio v26: 1 s / 1 kHz tone, peak=320/32768, ramped; keep speaker away from ears");
  if (op == BK7258_AUDIO_RECORD)
    puts("Audio v26: recording MIC1 for 1 s after 200 ms settling; RAM only, speak now");
  if (op == BK7258_AUDIO_PLAY)
    printf("Audio v26: replay 1 s, DC removed, attenuated %ux, "
           "peak limited to 1024/32768; keep speaker away from ears\n", divisor);
  if (op == BK7258_AUDIO_SILENCE)
    puts("Audio v26: 1 s zero PCM, DAC/PA enabled at unchanged gains; keep speaker away from ears");
  ret = op == BK7258_AUDIO_PLAY ? bk7258_audio_replay(divisor, &report) :
                                bk7258_audio_diag(op, &report);
  if (ret == -ENODATA) puts("Audio: no recording; run xiaopai audio record first");
  printf("Audio v26 %s: result=%d id=0x%08" PRIx32
         " samples=%" PRIu32 " irq=%" PRIu32 " fifo_faults=%" PRIu32
         " recorded=%" PRIu32 "\n", names[op], ret, report.device_id,
         report.samples, report.interrupts, report.fifo_faults, report.recorded);
  if (report.interrupts != 0 || op == BK7258_AUDIO_RECORD)
    {
      printf("FIFO: raw_samples=%" PRIu32 " elapsed_ms=%" PRIu32
             " max_batch=%" PRIu32 " max_irq_gap_ms=%" PRIu32
             " tick_us=%u\n",
             report.raw_samples, report.elapsed_ms, report.max_batch,
             report.max_irq_gap_ms, (unsigned int)CONFIG_USEC_PER_TICK);
      printf("FIFO: before_or=0x%08" PRIx32 " after_or=0x%08" PRIx32
             " adc_threshold=%" PRIu32 " full_after=%" PRIu32
             " empty_after=%" PRIu32 "\n", report.status_before_or,
             report.status_after_or, report.adc_threshold, report.full_after,
             report.empty_after);
    }
  if (report.fifo_faults != 0)
    puts("Audio warning: FIFO boundary observed; not a dropped-sample count or a quality pass");
  if (report.recorded != 0 && (op == BK7258_AUDIO_RECORD ||
      op == BK7258_AUDIO_PLAY || op == BK7258_AUDIO_STATUS))
    printf("MIC1 raw PCM: dc=%" PRId32 " rms=%" PRIu32 " peak=%" PRIu32
           " clipped=%" PRIu32 "\n", report.dc, report.rms, report.peak,
           report.clipped);
  if (op == BK7258_AUDIO_STATUS)
    puts("Local ADC/DAC diagnostic only; no /dev/audio stream or cloud audio yet");
  return ret;
usage:
  puts("xiaopai audio status|tone|silence|record|play [8|4|2|1]|dump|clear");
  return -EINVAL;
}
