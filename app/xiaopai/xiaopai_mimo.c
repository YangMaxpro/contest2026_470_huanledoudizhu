/* SPDX-License-Identifier: Apache-2.0 */
#include <nuttx/config.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <pthread.h>
#include <poll.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>
#include "netutils/cJSON.h"
#include "xiaopai_httpcheck.h"
#include "xiaopai_mimo.h"

#ifndef XIAOPAI_MIMO_URL
#define XIAOPAI_MIMO_URL "https://api.xiaomimimo.com/v1/chat/completions"
#endif
#define XIAOPAI_TOKEN_PLAN_URL \
  "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
#define MIMO_KEY_MAX 256
#define MIMO_PROMPT_MAX 512
#define MIMO_RESPONSE_MAX 8192

static pthread_mutex_t g_mimo_lock = PTHREAD_MUTEX_INITIALIZER;
static char g_key[MIMO_KEY_MAX + 1];
static const char *g_model = "mimo-v2.5";
static unsigned int g_requests;
static unsigned int g_successes;
static int g_last_error;

static int64_t mimo_now(void)
{
  struct timespec ts;
  if (clock_gettime(CLOCK_MONOTONIC, &ts) < 0)
    return -1;
  return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static bool valid_key(const char *key)
{
  size_t n = strlen(key);
  size_t i;
  bool token_plan = strncmp(key, "tp-", 3) == 0;
  bool payg = strncmp(key, "sk-", 3) == 0;
  if (n < 4 || n > MIMO_KEY_MAX || (!token_plan && !payg))
    return false;
  for (i = 3; i < n; i++)
    {
      unsigned char c = key[i];
      if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
            (c >= '0' && c <= '9') || c == '-' || c == '_'))
        return false;
    }
  return true;
}

static int read_key(void)
{
  char key[MIMO_KEY_MAX + 1] = {0};
  size_t used = 0;
  bool overflow = false;
  bool started = false;
  int ret = 0;
  int input_fd = STDIN_FILENO;
  int console_fd = -1;

  /* NSH may expose a one-shot command pipe as fd 0. Re-open the active
   * console so the hidden prompt owns the UART input until newline instead of
   * seeing EOF and returning the key line to NSH as a new command. */
  console_fd = open("/dev/console", O_RDWR);
  if (console_fd >= 0)
    input_fd = console_fd;
#ifdef CONFIG_SERIAL_TERMIOS
  struct termios saved;
  struct termios hidden;
  if (tcgetattr(input_fd, &saved) < 0)
    {
      if (console_fd >= 0) close(console_fd);
      return -errno;
    }
  hidden = saved;
  hidden.c_lflag &= ~(ECHO | ECHONL | ICANON | ISIG);
  hidden.c_cc[VMIN] = 1;
  hidden.c_cc[VTIME] = 0;
  if (tcsetattr(input_fd, TCSANOW, &hidden) < 0)
    {
      if (console_fd >= 0) close(console_fd);
      return -errno;
    }
#endif
  /* Without SERIAL_TERMIOS the serial driver has no echo; bypass NSH's
   * readline so credentials never enter command history or task arguments. */
  printf("MiMo API key (sk-/tp-, hidden, RAM only; local echo must be off): ");
  fflush(stdout);
  for (;;)
    {
      char c;
      ssize_t n = read(input_fd, &c, 1);
      if (n < 0 && errno == EINTR)
        continue;
      if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
        {
          struct pollfd fd = { .fd = input_fd, .events = POLLIN };
          int ready = poll(&fd, 1, 1000);
          if (ready < 0 && errno != EINTR)
            {
              ret = -errno;
              break;
            }
          continue;
        }
      if (n <= 0)
        {
          /* Some UART-backed stdin implementations report a transient zero
           * read between NSH lines. Keep the hidden prompt alive until the
           * operator submits a key or sends Ctrl-C/Ctrl-D. */
          if (n == 0)
            {
              struct pollfd fd = { .fd = input_fd, .events = POLLIN };
              int ready = poll(&fd, 1, 1000);
              if (ready >= 0 || errno == EINTR)
                continue;
            }
          ret = n == 0 ? -ECANCELED : -errno;
          break;
        }
      if (c == '\r' || c == '\n')
        {
          /* The UART can deliver the NSH command's line terminator after the
           * app has opened /dev/console. Ignore that leading terminator; a
           * newline after the first key character still submits the input. */
          if (!started)
            continue;
          break;
        }
      if (c == 3 || c == 4)
        {
          ret = -ECANCELED;
          break;
        }
      if (c == '\b' || c == 127)
        {
          if (used > 0)
            key[--used] = 0;
          continue;
        }
      if (used == MIMO_KEY_MAX)
        overflow = true;
      else
        {
          key[used++] = c;
          started = true;
        }
      if (c == 0)
        overflow = true;
    }
#ifdef CONFIG_SERIAL_TERMIOS
  if (tcsetattr(input_fd, TCSANOW, &saved) < 0)
    ret = -errno;
#endif
  if (console_fd >= 0)
    close(console_fd);
  printf("\n");
  if (ret == 0 && (overflow || !valid_key(key)))
    ret = -EINVAL;
  if (ret == 0)
    {
      explicit_bzero(g_key, sizeof(g_key));
      memcpy(g_key, key, used);
      printf("MiMo key configured in RAM; cleared on reboot or cloud clear\n");
    }
  else
    {
      printf("MiMo key not changed: invalid or cancelled input (sk- or tp- key required)\n");
    }
  explicit_bzero(key, sizeof(key));
  return ret;
}

/* Bound recursion and node count before cJSON allocates a response tree.
 * This is only a resource guard; cJSON performs actual JSON validation. */
static bool json_bounded(const char *data, size_t n)
{
  unsigned int depth = 0;
  unsigned int tokens = 0;
  bool quoted = false;
  bool escaped = false;
  size_t i;
  for (i = 0; i < n; i++)
    {
      char c = data[i];
      if (c == 0)
        return false;
      if (quoted)
        {
          if (escaped)
            {
              if (c == 'u' && i + 4 < n && memcmp(data + i + 1, "0000", 4) == 0)
                return false;
              escaped = false;
            }
          else if (c == '\\')
            escaped = true;
          else if (c == '"')
            quoted = false;
          continue;
        }
      if (c == '"')
        quoted = true;
      else if (c == '{' || c == '[')
        {
          if (++depth > 12)
            return false;
        }
      else if (c == '}' || c == ']')
        {
          if (depth == 0)
            return false;
          depth--;
        }
      if ((c == ',' || c == ':') && ++tokens > 256)
        return false;
    }
  return !quoted && depth == 0;
}

static char *make_request(const char *prompt)
{
  static const char base[] =
    "{\"messages\":[{\"role\":\"system\",\"content\":"
    "\"You are XiaoPai, a home assistant powered by Xiaomi MiMo. "
    "Reply briefly in the user's language. You cannot execute device actions.\"},"
    "{\"role\":\"user\"}],\"stream\":false,\"max_completion_tokens\":256,"
    "\"thinking\":{\"type\":\"disabled\"}}";
  cJSON *root = cJSON_Parse(base);
  cJSON *user;
  char *body = NULL;
  if (root == NULL)
    return NULL;
  user = cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(root, "messages"), 1);
  if (cJSON_AddStringToObject(root, "model", g_model) != NULL &&
      cJSON_AddStringToObject(user, "content", prompt) != NULL)
    body = cJSON_PrintUnformatted(root);
  cJSON_Delete(root);
  return body;
}

static int parse_answer(const char *data, size_t n, char *out, size_t capacity)
{
  cJSON *root;
  cJSON *choices;
  cJSON *choice;
  cJSON *message;
  cJSON *content;
  cJSON *finish;
  const unsigned char *p;
  int ret = -EPROTO;
  if (n == 0 || !json_bounded(data, n))
    return -EPROTO;
  root = cJSON_ParseWithOpts(data, NULL, true);
  if (root == NULL)
    return -EPROTO;
  choices = cJSON_GetObjectItemCaseSensitive(root, "choices");
  choice = cJSON_GetArrayItem(choices, 0);
  message = cJSON_GetObjectItemCaseSensitive(choice, "message");
  content = cJSON_GetObjectItemCaseSensitive(message, "content");
  finish = cJSON_GetObjectItemCaseSensitive(choice, "finish_reason");
  if (!cJSON_IsObject(root) || !cJSON_IsArray(choices) ||
      cJSON_GetArraySize(choices) != 1 || !cJSON_IsString(content) ||
      !cJSON_IsString(finish) || content->valuestring[0] == '\0')
    goto out;
  if (strcmp(finish->valuestring, "length") == 0)
    {
      ret = -EFBIG;
      goto out;
    }
  if (strcmp(finish->valuestring, "stop") != 0 ||
      (g_key[0] != 0 && strstr(content->valuestring, g_key) != NULL))
    goto out;
  if (out != NULL)
    {
      size_t length = strlen(content->valuestring);
      if (length >= capacity) { ret = -EFBIG; goto out; }
      memcpy(out, content->valuestring, length + 1);
      ret = 0;
      goto out;
    }
  printf("XiaoPai: ");
  for (p = (const unsigned char *)content->valuestring; *p != 0; p++)
    {
      /* Never interpret model text as terminal escape/control sequences. */
      if (*p == 0xc2 && p[1] >= 0x80 && p[1] <= 0x9f)
        { p++; continue; }
      putchar((*p < 0x20 && *p != '\n' && *p != '\t') || *p == 0x7f ? ' ' : *p);
    }
  putchar('\n');
  ret = 0;
out:
  cJSON_Delete(root);
  return ret;
}

static int print_answer(const char *data, size_t n)
{
  return parse_answer(data, n, NULL, 0);
}

static const char *mimo_url(void)
{
  return strncmp(g_key, "tp-", 3) == 0 ? XIAOPAI_TOKEN_PLAN_URL :
         XIAOPAI_MIMO_URL;
}

#ifdef CONFIG_XIAOPAI_VOICE
bool xiaopai_mimo_json_bounded(const char *data, size_t size)
{
  return json_bounded(data, size);
}

/* One worker owns the key/model for the whole turn. No key copies escape this
 * module. cloud clear returns busy until cooperative stop has completed. */
int xiaopai_mimo_begin(void)
{
  int ret = pthread_mutex_trylock(&g_mimo_lock);
  if (ret != 0) return -ret;
  if (g_key[0] == 0)
    { pthread_mutex_unlock(&g_mimo_lock); return -EACCES; }
  return 0;
}

void xiaopai_mimo_end(void)
{
  pthread_mutex_unlock(&g_mimo_lock);
}

int xiaopai_mimo_post(struct xiaopai_http_post *post)
{
  char auth[MIMO_KEY_MAX + 16] = {0};
  const char *headers[] = {auth, "Content-Type: application/json",
                          "Accept: application/json, text/event-stream"};
  int ret;
  snprintf(auth, sizeof(auth), "api-key: %s", g_key);
  post->headers = headers;
  post->nheaders = 3;
  g_requests++;
  ret = xiaopai_https_post(mimo_url(), post);
  post->headers = NULL;
  post->nheaders = 0;
  explicit_bzero(auth, sizeof(auth));
  g_last_error = ret < 0 ? -ret : 0;
  return ret;
}

int xiaopai_mimo_extract(const char *data, size_t n, char *text, size_t capacity)
{
  if (text == NULL || capacity == 0) return -EINVAL;
  text[0] = 0;
  return parse_answer(data, n, text, capacity);
}

int xiaopai_mimo_reply(const char *prompt, char *reply, size_t capacity,
                       bool (*cancelled)(void *), void *arg)
{
  char *body = NULL;
  char *response = NULL;
  struct xiaopai_http_post post = {0};
  int ret = -ENOMEM;
  if (prompt == NULL || strlen(prompt) > MIMO_PROMPT_MAX) return -E2BIG;
  body = make_request(prompt);
  response = malloc(MIMO_RESPONSE_MAX + 1);
  if (body == NULL || response == NULL) goto out;
  post.body = body;
  post.response = response;
  post.capacity = MIMO_RESPONSE_MAX + 1;
  post.cancelled = cancelled;
  post.arg = arg;
  ret = xiaopai_mimo_post(&post);
  if (ret == 0) ret = xiaopai_mimo_extract(response, post.bytes, reply, capacity);
out:
  if (body != NULL) { explicit_bzero(body, strlen(body)); cJSON_free(body); }
  if (response != NULL) { explicit_bzero(response, MIMO_RESPONSE_MAX + 1); free(response); }
  return ret;
}
#endif

int xiaopai_cloud(int argc, char **argv)
{
  int ret = pthread_mutex_trylock(&g_mimo_lock);
  if (ret != 0)
    { printf("MiMo busy\n"); return -ret; }
  ret = 0;
  if (argc == 1 && strcmp(argv[0], "status") == 0)
    printf("MiMo v22: model=%s key=%s requests=%u text_successes=%u last_error=%d\n"
           "Text: single-turn, thinking=disabled; no automatic retries\n",
           g_model, g_key[0] ? "configured (RAM)" : "missing",
           g_requests, g_successes, g_last_error);
  else if (argc == 1 && strcmp(argv[0], "key") == 0)
    ret = read_key();
  else if (argc == 1 && strcmp(argv[0], "clear") == 0)
    { explicit_bzero(g_key, sizeof(g_key)); printf("MiMo key cleared\n"); }
  else if (argc == 2 && strcmp(argv[0], "model") == 0 &&
           (!strcmp(argv[1], "mimo-v2.5") || !strcmp(argv[1], "mimo-v2.5-pro")))
    {
      g_model = !strcmp(argv[1], "mimo-v2.5") ? "mimo-v2.5" : "mimo-v2.5-pro";
      printf("MiMo model=%s\n", g_model);
    }
  else
    {
      printf("Usage: xiaopai cloud status|key|clear|model <mimo-v2.5|mimo-v2.5-pro>\n");
      ret = -EINVAL;
    }
  pthread_mutex_unlock(&g_mimo_lock);
  return ret;
}

int xiaopai_mimo_ask(int argc, char **argv)
{
  char prompt[MIMO_PROMPT_MAX + 1] = {0};
  char auth[MIMO_KEY_MAX + 16] = {0};
  const char *headers[] = {auth, "Content-Type: application/json", "Accept: application/json"};
  struct xiaopai_http_post post = {0};
  char *body = NULL;
  char *response = NULL;
  size_t used = 0;
  int64_t started;
  int i;
  int ret = pthread_mutex_trylock(&g_mimo_lock);
  if (ret != 0)
    { printf("MiMo busy\n"); return -ret; }
  if (argc == 0)
    { ret = -EINVAL; goto done; }
  for (i = 0; i < argc; i++)
    {
      size_t len = strlen(argv[i]);
      size_t separator = i != 0;
      if (len + separator > MIMO_PROMPT_MAX - used)
        { ret = -E2BIG; goto done; }
      if (separator)
        prompt[used++] = ' ';
      memcpy(prompt + used, argv[i], len);
      used += len;
    }
  if (used == 0)
    { ret = -EINVAL; goto done; }
  if (g_key[0] == '\0')
    { printf("Configure a key with xiaopai cloud key first\n"); ret = -EACCES; goto done; }
  started = mimo_now();
  if (started < 0)
    { ret = -EIO; goto done; }
  body = make_request(prompt);
  response = malloc(MIMO_RESPONSE_MAX + 1);
  if (body == NULL || response == NULL)
    { ret = -ENOMEM; goto done; }
  snprintf(auth, sizeof(auth), "api-key: %s", g_key);
  post.body = body;
  post.headers = headers;
  post.nheaders = sizeof(headers) / sizeof(headers[0]);
  post.response = response;
  post.capacity = MIMO_RESPONSE_MAX + 1;
  g_requests++;
  printf("MiMo request: model=%s max_tokens=256 thinking=disabled\n", g_model);
  ret = xiaopai_https_post(mimo_url(), &post);
  printf("MiMo request elapsed_ms=%" PRId64 " status=%u bytes=%zu\n",
         mimo_now() - started, post.status, post.bytes);
  if (ret == 0)
    ret = print_answer(response, post.bytes);
  else if (post.status == 401 || post.status == 403)
    printf("MiMo authentication/permission failed; check key and account\n");
  else if (post.status == 402)
    printf("MiMo account quota/balance unavailable\n");
  else if (post.status == 429)
    printf("MiMo rate limited; wait before manually retrying\n");
  if (ret == 0)
    g_successes++;
done:
  if (ret < 0)
    printf("MiMo request failed: error=%d; no reply accepted\n", -ret);
  g_last_error = ret < 0 ? -ret : 0;
  explicit_bzero(auth, sizeof(auth));
  explicit_bzero(prompt, sizeof(prompt));
  if (body != NULL)
    { explicit_bzero(body, strlen(body)); cJSON_free(body); }
  if (response != NULL)
    { explicit_bzero(response, MIMO_RESPONSE_MAX + 1); free(response); }
  pthread_mutex_unlock(&g_mimo_lock);
  return ret;
}
