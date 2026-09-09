/* SPDX-License-Identifier: Apache-2.0 */
#include <nuttx/config.h>
#include <arch/chip/bk7258_pcm.h>
#include <arch/chip/bk7258_psram.h>
#include <errno.h>
#include <inttypes.h>
#include <pthread.h>
#include <sched.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "mbedtls/base64.h"
#include "netutils/cJSON.h"
#include "xiaopai_httpcheck.h"
#include "xiaopai_mimo.h"
#include "xiaopai_voice.h"

#define VOICE_EVENT_MAX 32768u
#define VOICE_TEXT_MAX 2048u
#define VOICE_TTS_RATE 24000u
#define VOICE_TTS_MAX (VOICE_TTS_RATE * 45u)

static const char g_asr_prefix[] =
  "{\"model\":\"mimo-v2.5-asr\",\"stream\":false,"
  "\"asr_options\":{\"language\":\"auto\"},\"messages\":[{\"role\":\"user\","
  "\"content\":[{\"type\":\"input_audio\",\"input_audio\":{"
  "\"data\":\"data:audio/wav;base64,";
static const char g_asr_suffix[] = "\"}}]}]}";

struct voice_turn
{
  unsigned int seconds;
  uint32_t session;
  int64_t deadline;
  size_t raw_offset;
  size_t raw_length;
  size_t source_offset;
  unsigned char wav[44];
  int16_t *recording;
  bool captured;
  char encoded[257];
  size_t encoded_pos;
  size_t encoded_size;
  char *event;
  size_t event_size;
  size_t line_size;
  char prefix[5];
  bool data_line;
  bool skip_space;
  bool skip_lf;
  bool had_data;
  bool finished;
  bool done;
  uint32_t played;
};

static pthread_mutex_t g_voice_lock = PTHREAD_MUTEX_INITIALIZER;
static bool g_running;
static bool g_cancel;
static const char *g_stage = "idle";
static int g_result;
static unsigned int g_turns;
static unsigned int g_completed;
static uint32_t g_played;
static struct voice_turn *g_pending;

static int64_t voice_now(void)
{
  struct timespec ts;
  if (clock_gettime(CLOCK_MONOTONIC, &ts) < 0) return -1;
  return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static bool voice_cancelled(void *arg)
{
  bool cancel;
  (void)arg;
  pthread_mutex_lock(&g_voice_lock);
  cancel = g_cancel;
  pthread_mutex_unlock(&g_voice_lock);
  return cancel;
}

static void voice_stage(const char *stage)
{
  pthread_mutex_lock(&g_voice_lock);
  g_stage = stage;
  pthread_mutex_unlock(&g_voice_lock);
  printf("voice: %s\n", stage);
}

static int voice_check(struct voice_turn *turn)
{
  int64_t now = voice_now();
  if (voice_cancelled(turn)) return -ECANCELED;
  return now < 0 ? -EIO : now >= turn->deadline ? -ETIMEDOUT : 0;
}

static void put_le(unsigned char *p, uint32_t v, unsigned int bytes)
{
  while (bytes-- != 0) { *p++ = v & 255; v >>= 8; }
}

static void asr_init(struct voice_turn *turn)
{
  uint32_t bytes = turn->seconds * BK7258_PCM_RATE * 2;
  memcpy(turn->wav, "RIFF", 4);
  put_le(turn->wav + 4, 36 + bytes, 4);
  memcpy(turn->wav + 8, "WAVEfmt ", 8);
  put_le(turn->wav + 16, 16, 4);
  put_le(turn->wav + 20, 1, 2);
  put_le(turn->wav + 22, 1, 2);
  put_le(turn->wav + 24, BK7258_PCM_RATE, 4);
  put_le(turn->wav + 28, BK7258_PCM_RATE * 2, 4);
  put_le(turn->wav + 32, 2, 2);
  put_le(turn->wav + 34, 16, 2);
  memcpy(turn->wav + 36, "data", 4);
  put_le(turn->wav + 40, bytes, 4);
  turn->raw_length = sizeof(turn->wav) + bytes;
}

static int capture_health(struct voice_turn *turn)
{
  struct bk7258_pcm_status_s status;
  int ret = bk7258_pcm_status(turn->session, &status);
  if (ret < 0) return ret;
  if (status.error < 0) return status.error;
  if (!status.running) return -EIO;
  return status.dropped_samples != 0 ? -EOVERFLOW : 0;
}

/* Called only from the verified TLS body source. Drain capture independently
 * of network writes, then stop the microphone before returning any audio. */
static int asr_capture(struct voice_turn *turn)
{
  size_t count = turn->seconds * BK7258_PCM_RATE;
  size_t offset = 0;
  int ret = voice_check(turn);
  if (ret < 0) return ret;
  voice_stage("recording locally; speak now");
  printf("voice: %u s, 16 kHz mono; upload follows microphone stop\n", turn->seconds);
  ret = bk7258_pcm_start(true, &turn->session);
  if (ret < 0) return ret;
  while (offset < count)
    {
      ret = voice_check(turn);
      if (ret < 0) break;
      ret = capture_health(turn);
      if (ret < 0) break;
      size_t chunk = count - offset;
      if (chunk > 320) chunk = 320;
      ret = bk7258_pcm_read(turn->session, turn->recording + offset, chunk);
      if (ret == -EAGAIN)
        {
          if (usleep(10000) < 0 && errno != EINTR) { ret = -errno; break; }
          continue;
        }
      if (ret <= 0) { if (ret == 0) ret = -EIO; break; }
      if ((size_t)ret > chunk) { ret = -EPROTO; break; }
      offset += ret;
    }
  if (offset == count) ret = capture_health(turn);
  int stopped = bk7258_pcm_stop(turn->session);
  turn->session = 0;
  if (ret == 0) ret = stopped;
  if (ret == 0)
    {
      turn->captured = true;
      voice_stage("uploading recorded audio; microphone stopped");
    }
  return ret;
}

static int asr_encode(struct voice_turn *turn)
{
  unsigned char raw[192];
  size_t n = 0;
  size_t encoded;
  int ret;
  if (!turn->captured)
    {
      ret = asr_capture(turn);
      if (ret < 0) return ret;
    }
  ret = voice_check(turn);
  if (ret < 0) goto out;
  while (n < sizeof(raw) && turn->raw_offset < turn->raw_length)
    {
      if (turn->raw_offset < sizeof(turn->wav))
        raw[n++] = turn->wav[turn->raw_offset];
      else
        {
          size_t offset = turn->raw_offset - sizeof(turn->wav);
          uint16_t value = (uint16_t)turn->recording[offset / 2];
          raw[n++] = (unsigned char)(value >> ((offset & 1) * 8));
        }
      turn->raw_offset++;
    }
  ret = mbedtls_base64_encode((unsigned char *)turn->encoded,
                              sizeof(turn->encoded), &encoded, raw, n);
  if (ret != 0) { ret = -EIO; goto out; }
  turn->encoded_size = encoded;
  turn->encoded_pos = 0;
  if (turn->raw_offset == turn->raw_length)
    {
      explicit_bzero(turn->recording, turn->seconds * BK7258_PCM_RATE * 2);
      bk7258_psram_free(turn->recording);
      turn->recording = NULL;
      if (ret == 0) voice_stage("recognizing");
    }
out:
  explicit_bzero(raw, sizeof(raw));
  return ret;
}

static ssize_t asr_source(void *arg, char *buffer, size_t capacity)
{
  struct voice_turn *turn = arg;
  const size_t prefix = sizeof(g_asr_prefix) - 1;
  const size_t b64size = ((turn->raw_length + 2) / 3) * 4;
  const size_t total = prefix + b64size + sizeof(g_asr_suffix) - 1;
  size_t n = 0;
  int ret;
  if (capacity > 1024) capacity = 1024;
  ret = voice_check(turn);
  if (ret < 0) return ret;
  while (n < capacity && turn->source_offset < total)
    {
      if (turn->source_offset < prefix)
        buffer[n++] = g_asr_prefix[turn->source_offset];
      else if (turn->source_offset < prefix + b64size)
        {
          if (turn->encoded_pos == turn->encoded_size)
            {
              ret = asr_encode(turn);
              if (ret < 0) return ret;
            }
          buffer[n++] = turn->encoded[turn->encoded_pos++];
        }
      else
        buffer[n++] = g_asr_suffix[turn->source_offset - prefix - b64size];
      turn->source_offset++;
    }
  return (ssize_t)n;
}

static int play_samples(struct voice_turn *turn, const unsigned char *bytes, size_t n)
{
  int16_t samples[288];
  size_t offset = 0;
  int ret = 0;
  if ((n & 1) != 0 || n > sizeof(samples)) return -EPROTO;
  if (n / 2 > VOICE_TTS_MAX - turn->played) return -EFBIG;
  for (size_t i = 0; i < n / 2; i++)
    {
      int32_t value = (uint16_t)bytes[2 * i] | ((uint16_t)bytes[2 * i + 1] << 8);
      if (value >= 32768) value -= 65536;
      /* Cloud PCM can be full scale. Combined with core /4 this is /32,
       * keeping the existing peak protection without routine hard clipping. */
      samples[i] = value / 8;
    }
  if (turn->session == 0)
    {
      voice_stage("speaking (24 kHz; keep speaker away from ears)");
      ret = bk7258_pcm_start_rate(false, VOICE_TTS_RATE, &turn->session);
      if (ret < 0) goto out;
    }
  while (offset < n / 2)
    {
      ret = voice_check(turn);
      if (ret < 0) goto out;
      ret = bk7258_pcm_write(turn->session, samples + offset, n / 2 - offset);
      if (ret == -EAGAIN)
        {
          if (usleep(10000) < 0 && errno != EINTR) { ret = -errno; goto out; }
          continue;
        }
      if (ret <= 0) { if (ret == 0) ret = -EIO; goto out; }
      offset += ret;
    }
  turn->played += n / 2;
  ret = 0;
out:
  explicit_bzero(samples, sizeof(samples));
  return ret;
}

static int play_base64(struct voice_turn *turn, const char *s)
{
  unsigned char pcm[576];
  size_t length = strlen(s);
  size_t padding = 0;
  size_t decoded;
  int ret = -EPROTO;
  if (length == 0 || length % 4 != 0) return -EPROTO;
  if (s[length - 1] == '=') padding++;
  if (s[length - 2] == '=') padding++;
  if (((length / 4 * 3 - padding) & 1) != 0) return -EPROTO;
  for (size_t i = 0; i < length - padding; i++)
    if (!((s[i] >= 'A' && s[i] <= 'Z') || (s[i] >= 'a' && s[i] <= 'z') ||
          (s[i] >= '0' && s[i] <= '9') || s[i] == '+' || s[i] == '/'))
      return -EPROTO;
  for (size_t offset = 0; offset < length;)
    {
      size_t chunk = length - offset;
      if (chunk > 768) chunk = 768;
      if (mbedtls_base64_decode(pcm, sizeof(pcm), &decoded,
                                (const unsigned char *)s + offset, chunk) != 0)
        { ret = -EPROTO; goto out; }
      ret = play_samples(turn, pcm, decoded);
      if (ret < 0) goto out;
      offset += chunk;
    }
out:
  explicit_bzero(pcm, sizeof(pcm));
  return ret;
}

static void wipe_json_strings(cJSON *node)
{
  for (; node != NULL; node = node->next)
    {
      if (node->valuestring != NULL)
        explicit_bzero(node->valuestring, strlen(node->valuestring));
      if (node->child != NULL) wipe_json_strings(node->child);
    }
}

static int tts_event(struct voice_turn *turn)
{
  cJSON *root = NULL;
  cJSON *choices;
  cJSON *choice;
  cJSON *delta;
  cJSON *audio;
  cJSON *data;
  cJSON *finish;
  int ret = -EPROTO;
  if (turn->done) return -EPROTO;
  if (turn->event_size != 0 && turn->event[turn->event_size - 1] == '\n')
    turn->event_size--;
  turn->event[turn->event_size] = 0;
  if (strcmp(turn->event, "[DONE]") == 0)
    {
      if (!turn->finished || turn->played == 0) return -EPROTO;
      turn->done = true;
      return 0;
    }
  if (!xiaopai_mimo_json_bounded(turn->event, turn->event_size)) return -EPROTO;
  root = cJSON_ParseWithOpts(turn->event, NULL, true);
  if (!cJSON_IsObject(root) || cJSON_HasObjectItem(root, "error")) goto out;
  choices = cJSON_GetObjectItemCaseSensitive(root, "choices");
  if (!cJSON_IsArray(choices)) goto out;
  if (cJSON_GetArraySize(choices) == 0) { ret = 0; goto out; }
  if (cJSON_GetArraySize(choices) != 1) goto out;
  choice = cJSON_GetArrayItem(choices, 0);
  delta = cJSON_GetObjectItemCaseSensitive(choice, "delta");
  finish = cJSON_GetObjectItemCaseSensitive(choice, "finish_reason");
  if (!cJSON_IsObject(delta) || cJSON_HasObjectItem(delta, "tool_calls")) goto out;
  if (finish != NULL && !cJSON_IsNull(finish))
    {
      if (!cJSON_IsString(finish) || strcmp(finish->valuestring, "stop") != 0) goto out;
      if (turn->finished) goto out;
    }
  audio = cJSON_GetObjectItemCaseSensitive(delta, "audio");
  if (audio != NULL && !cJSON_IsNull(audio))
    {
      data = cJSON_GetObjectItemCaseSensitive(audio, "data");
      if (!cJSON_IsObject(audio) || !cJSON_IsString(data) || turn->finished) goto out;
      if (data->valuestring[0] != 0)
        {
          ret = play_base64(turn, data->valuestring);
          explicit_bzero(data->valuestring, strlen(data->valuestring));
          if (ret < 0) goto out;
        }
    }
  if (cJSON_IsString(finish)) turn->finished = true;
  ret = 0;
out:
  wipe_json_strings(root);
  cJSON_Delete(root);
  return ret;
}

static int event_char(struct voice_turn *turn, char c)
{
  if (turn->event_size == VOICE_EVENT_MAX) return -EFBIG;
  turn->event[turn->event_size++] = c;
  return 0;
}

/* SSE framing is incremental across arbitrary socket splits, CRLF and
 * multiple data lines. JSON itself is validated by cJSON per bounded event. */
static int tts_sink(void *arg, const char *bytes, size_t length)
{
  struct voice_turn *turn = arg;
  int ret;
  for (size_t i = 0; i < length; i++)
    {
      ret = voice_check(turn);
      if (ret < 0) return ret;
      char c = bytes[i];
      if (c == 0) return -EPROTO;
      if (turn->skip_lf && c == '\n') { turn->skip_lf = false; continue; }
      turn->skip_lf = c == '\r';
      if (c == '\r') c = '\n';
      if (c == '\n')
        {
          if (turn->line_size == 0 && turn->had_data)
            {
              ret = tts_event(turn);
              explicit_bzero(turn->event, turn->event_size);
              turn->event_size = 0;
              turn->had_data = false;
              if (ret < 0) return ret;
            }
          else if (turn->data_line)
            {
              ret = event_char(turn, '\n');
              if (ret < 0) return ret;
            }
          turn->line_size = 0;
          turn->data_line = false;
          turn->skip_space = false;
          continue;
        }
      if (turn->line_size < sizeof(turn->prefix))
        {
          turn->prefix[turn->line_size] = c;
          if (turn->line_size == 4 && memcmp(turn->prefix, "data:", 5) == 0)
            {
              turn->data_line = true;
              turn->had_data = true;
              turn->skip_space = true;
            }
        }
      else if (turn->data_line)
        {
          bool skip = turn->skip_space && c == ' ';
          turn->skip_space = false;
          if (!skip)
            {
              ret = event_char(turn, c);
              if (ret < 0) return ret;
            }
        }
      if (++turn->line_size > VOICE_EVENT_MAX) return -EFBIG;
    }
  return 0;
}

static char *tts_request(const char *text)
{
  cJSON *root = cJSON_Parse("{\"model\":\"mimo-v2.5-tts\",\"stream\":true,"
                           "\"messages\":[{\"role\":\"assistant\"}],"
                           "\"audio\":{\"format\":\"pcm16\",\"voice\":\"mimo_default\"}}");
  char *body = NULL;
  if (root == NULL) return NULL;
  cJSON *message = cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(root, "messages"), 0);
  if (cJSON_AddStringToObject(message, "content", text) != NULL)
    body = cJSON_PrintUnformatted(root);
  cJSON_Delete(root);
  return body;
}

static void display_text(const char *label, const char *text)
{
  const unsigned char *p = (const unsigned char *)text;
  printf("%s: ", label);
  for (; *p != 0; p++)
    {
      if (*p == 0xc2 && p[1] >= 0x80 && p[1] <= 0x9f) { p++; continue; }
      putchar(*p < 0x20 || *p == 0x7f ? ' ' : *p);
    }
  putchar('\n');
}

static int voice_worker(int argc, char **argv)
{
  struct voice_turn *turn;
  struct xiaopai_http_post post = {0};
  char transcript[513] = {0};
  char reply[VOICE_TEXT_MAX + 1] = {0};
  char *response = NULL;
  char *body = NULL;
  bool reserved = false;
  int ret;
  (void)argc;
  (void)argv;
  pthread_mutex_lock(&g_voice_lock);
  turn = g_pending;
  g_pending = NULL;
  pthread_mutex_unlock(&g_voice_lock);
  /* Only voice stop is supported: asynchronous cancellation cannot safely
   * unwind hardware ownership or an in-flight HTTP parser. */
  task_setcancelstate(TASK_CANCEL_DISABLE, NULL);
  ret = xiaopai_mimo_begin();
  if (ret < 0) goto out;
  reserved = true;
  if (time(NULL) < 1735689600) { ret = -ETIME; goto out; }
  response = malloc(8193);
  if (response == NULL) { ret = -ENOMEM; goto out; }
  asr_init(turn);
  turn->recording = bk7258_psram_malloc(turn->seconds * BK7258_PCM_RATE * 2);
  if (turn->recording == NULL) { ret = -ENOMEM; goto out; }
  turn->deadline = voice_now() + 60000;
  voice_stage("connecting ASR; recording starts only after verified TLS");
  post.source = asr_source;
  post.body_length = sizeof(g_asr_prefix) - 1 + ((turn->raw_length + 2) / 3) * 4 +
                     sizeof(g_asr_suffix) - 1;
  post.response = response;
  post.capacity = 8193;
  post.cancelled = voice_cancelled;
  post.arg = turn;
  ret = xiaopai_mimo_post(&post);
  if (ret == 0) ret = xiaopai_mimo_extract(response, post.bytes, transcript, sizeof(transcript));
  explicit_bzero(response, 8193);
  free(response);
  response = NULL;
  if (ret < 0) goto out;
  if (turn->source_offset != post.body_length || turn->session != 0)
    { ret = -EPROTO; goto out; }
  display_text("You", transcript);
  voice_stage("thinking");
  ret = voice_cancelled(turn) ? -ECANCELED :
        xiaopai_mimo_reply(transcript, reply, sizeof(reply), voice_cancelled, turn);
  explicit_bzero(transcript, sizeof(transcript));
  if (ret < 0) goto out;
  display_text("XiaoPai", reply);
  body = tts_request(reply);
  explicit_bzero(reply, sizeof(reply));
  turn->event = malloc(VOICE_EVENT_MAX + 1);
  if (body == NULL || turn->event == NULL) { ret = -ENOMEM; goto out; }
  voice_stage("synthesizing");
  memset(&post, 0, sizeof(post));
  post.body = body;
  post.sink = tts_sink;
  post.response_limit = 4 * 1024 * 1024;
  post.cancelled = voice_cancelled;
  post.arg = turn;
  turn->deadline = voice_now() + 60000;
  ret = xiaopai_mimo_post(&post);
  if (ret == 0 && (!turn->done || turn->had_data || turn->line_size != 0)) ret = -EPROTO;
  if (ret == 0) ret = voice_check(turn);
  if (ret == 0) ret = bk7258_pcm_drain(turn->session, 2000);
  if (ret == 0 && voice_cancelled(turn)) ret = -ECANCELED;
out:
  if (turn->session != 0)
    {
      struct bk7258_pcm_status_s status;
      if (bk7258_pcm_status(turn->session, &status) == 0 && !status.capture)
        printf("voice: playback samples=%" PRIu32 " inserted_silence=%" PRIu64 "\n",
               turn->played, status.silence_samples);
      int stopped = bk7258_pcm_stop(turn->session);
      if (ret == 0) ret = stopped;
    }
  if (reserved) xiaopai_mimo_end();
  if (turn->recording != NULL)
    {
      explicit_bzero(turn->recording, turn->seconds * BK7258_PCM_RATE * 2);
      bk7258_psram_free(turn->recording);
    }
  if (response != NULL) { explicit_bzero(response, 8193); free(response); }
  if (body != NULL) { explicit_bzero(body, strlen(body)); cJSON_free(body); }
  if (turn->event != NULL) { explicit_bzero(turn->event, VOICE_EVENT_MAX + 1); free(turn->event); }
  explicit_bzero(transcript, sizeof(transcript));
  explicit_bzero(reply, sizeof(reply));
  uint32_t played = turn->played;
  explicit_bzero(turn, sizeof(*turn));
  free(turn);
  if (ret == -EACCES) puts("voice: configure xiaopai cloud key first (RAM only)");
  if (ret == -ETIME) puts("voice: set accurate UTC with date -u -s first");
  if (ret == -EOVERFLOW) puts("voice: capture ring overrun; request aborted, no retry; sent audio cannot be recalled");
  printf("voice: %s result=%d; microphone/speaker stopped, audio buffers cleared\n",
         ret == 0 ? "complete" : ret == -ECANCELED ? "cancelled" : "failed", ret);
  pthread_mutex_lock(&g_voice_lock);
  g_result = ret;
  g_played = played;
  if (ret == 0) g_completed++;
  g_stage = ret == 0 ? "complete" : ret == -ECANCELED ? "cancelled" : "failed";
  g_running = false;
  pthread_mutex_unlock(&g_voice_lock);
  return ret == 0 ? 0 : 1;
}

int xiaopai_voice(int argc, char **argv)
{
  unsigned int seconds = 3;
  int ret = 0;
  if (argc == 1 && strcmp(argv[0], "status") == 0)
    {
      pthread_mutex_lock(&g_voice_lock);
      printf("voice v35: running=%d stage=%s turns=%u completed=%u result=%d played=%" PRIu32 "\n",
             g_running, g_stage, g_turns, g_completed, g_result, g_played);
      pthread_mutex_unlock(&g_voice_lock);
      return 0;
    }
  if (argc == 1 && strcmp(argv[0], "stop") == 0)
    {
      pthread_mutex_lock(&g_voice_lock);
      if (g_running) g_cancel = true;
      pthread_mutex_unlock(&g_voice_lock);
      puts("voice: stop requested; wait for running=0 before cloud clear (DNS may delay stop)");
      return 0;
    }
  if ((argc != 1 && argc != 2) || strcmp(argv[0], "start") != 0) goto usage;
  if (argc == 2)
    {
      char *end;
      unsigned long value = strtoul(argv[1], &end, 10);
      if (argv[1][0] < '0' || argv[1][0] > '9' || *end != 0 || value < 1 || value > 10) goto usage;
      seconds = value;
    }
  pthread_mutex_lock(&g_voice_lock);
  if (g_running) { pthread_mutex_unlock(&g_voice_lock); return -EBUSY; }
  /* Reserve only for this preflight, then the worker takes its own lock. */
  ret = xiaopai_mimo_begin();
  if (ret == 0) xiaopai_mimo_end();
  if (ret == 0 && time(NULL) < 1735689600) ret = -ETIME;
  if (ret < 0)
    {
      pthread_mutex_unlock(&g_voice_lock);
      puts("voice: requires cloud key, accurate UTC and an idle MiMo client");
      return ret;
    }
  struct voice_turn *turn = calloc(1, sizeof(*turn));
  if (turn == NULL) { pthread_mutex_unlock(&g_voice_lock); return -ENOMEM; }
  turn->seconds = seconds;
  g_pending = turn;
  g_running = true;
  g_cancel = false;
  g_stage = "starting";
  g_result = 0;
  /* An independent NuttX task survives the short-lived NSH command group. */
  pid_t pid = task_create("xiaopai_voice", 100, 16384, voice_worker, NULL);
  if (pid < 0)
    {
      ret = errno;
      g_running = false;
      g_pending = NULL;
      free(turn);
    }
  else g_turns++;
  pthread_mutex_unlock(&g_voice_lock);
  if (ret == 0) puts("voice: one turn started; ASR/model/TTS use Xiaomi API quota; no automatic retries");
  return -ret;
usage:
  puts("Usage: xiaopai voice start [1..10 seconds]|stop|status");
  return -EINVAL;
}
