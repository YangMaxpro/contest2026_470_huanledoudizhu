/* SPDX-License-Identifier: Apache-2.0 */

#include <nuttx/config.h>
#include <errno.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "netutils/webclient.h"
#include "xiaopai_httpcheck.h"
#ifdef CONFIG_XIAOPAI_HTTPSCHECK
#include <pthread.h>
#include "xiaopai_tls.h"
static pthread_mutex_t g_https_lock = PTHREAD_MUTEX_INITIALIZER;
#endif

#define HTTP_BUFFER_SIZE 2048
#define HTTP_BODY_LIMIT 32768
#ifndef XIAOPAI_HTTP_TIMEOUT_MS
#define XIAOPAI_HTTP_TIMEOUT_MS 30000
#endif
#ifndef XIAOPAI_HTTPS_TIMEOUT_MS
#define XIAOPAI_HTTPS_TIMEOUT_MS 60000
#endif

struct httpcheck_s
{
  struct webclient_context client;
  int64_t deadline;
  size_t bytes;
  bool headers_seen;
  struct xiaopai_http_post *post;
};

static int64_t monotonic_ms(void)
{
  struct timespec now;

  if (clock_gettime(CLOCK_MONOTONIC, &now) < 0)
    {
      return -1;
    }
  return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

static int time_left(const struct httpcheck_s *check)
{
  if (check->post != NULL && check->post->cancelled != NULL &&
      check->post->cancelled(check->post->arg))
    return -ECANCELED;
  int64_t now = monotonic_ms();
  int64_t remaining;

  if (now < 0)
    {
      return -EIO;
    }
  remaining = check->deadline - now;
  return remaining > 0 ? (int)remaining : -ETIMEDOUT;
}

static int receive_header(const char *line, bool truncated, void *arg)
{
  struct httpcheck_s *check = arg;
  int ret = time_left(check);

  (void)line;
  if (ret < 0)
    {
      return ret;
    }
  if (!check->headers_seen)
    {
      printf("HTTP response status=%u\n", check->client.http_status);
      check->headers_seen = true;
    }
  /* Do not follow a response to a different host or silently downgrade TLS. */
  if (check->client.http_status / 100 == 3)
    {
      return -ELOOP;
    }
  return truncated ? -EOVERFLOW : 0;
}

static int receive_body(char **buffer, int offset, int end,
                        int *buflen, void *arg)
{
  struct httpcheck_s *check = arg;
  int ret = time_left(check);

  if (ret < 0)
    {
      return ret;
    }
  if (buffer == NULL || *buffer == NULL || offset < 0 ||
      end < offset || end > *buflen)
    {
      return -EPROTO;
    }
  size_t limit = check->post != NULL && check->post->sink != NULL ?
                 check->post->response_limit : HTTP_BODY_LIMIT;
  if ((size_t)(end - offset) > limit - check->bytes)
    {
      return -EFBIG;
    }
  check->bytes += end - offset;
  if (check->post != NULL)
    {
      struct xiaopai_http_post *post = check->post;
      size_t count = end - offset;
      if (post->sink != NULL)
        {
          if (check->client.http_status / 100 != 2) return -EPROTO;
          ret = post->sink(post->arg, *buffer + offset, count);
          if (ret < 0) return ret;
          post->bytes += count;
          return 0;
        }
      if (count >= post->capacity - post->bytes)
        return -EFBIG;
      memcpy(post->response + post->bytes, *buffer + offset, count);
      post->bytes += count;
      post->response[post->bytes] = '\0';
    }
  return 0;
}

static int send_body(void *buffer, size_t *size, const void **data,
                     size_t requested, void *arg)
{
  struct httpcheck_s *check = arg;
  ssize_t count;
  int ret = time_left(check);
  if (ret < 0) return ret;
  if (*size > requested) *size = requested;
  count = check->post->source(check->post->arg, buffer, *size);
  if (count < 0) return (int)count;
  if (count == 0 || (size_t)count > *size) return -EPROTO;
  *size = count;
  *data = buffer;
  return 0;
}

static int run_check(const char *url, bool secure,
                     struct xiaopai_http_post *post)
{
  struct httpcheck_s check = {0};
#ifdef CONFIG_XIAOPAI_HTTPSCHECK
  struct xiaopai_tls *tls = NULL;
#endif
  const char *label = post != NULL ? "HTTPS POST" : (secure ? "HTTPS" : "HTTP");
  const char *scheme = secure ? "https://" : "http://";
  size_t scheme_len = strlen(scheme);
  const unsigned char *p;
  const char *stage = "resolve/connect/send";
  char *buffer;
  int ret;

  check.post = post;

  if (url == NULL || strncmp(url, scheme, scheme_len) != 0 ||
      strlen(url) > 200 || url[scheme_len] == '\0')
    {
      printf("%s check: expected %s URL\n", label, scheme);
      return -EINVAL;
    }
  for (p = (const unsigned char *)url; *p != '\0'; p++)
    {
      if (*p <= 0x20 || *p >= 0x7f || *p == '@')
        {
          printf("httpcheck: credentials/control characters are not allowed\n");
          return -EINVAL;
        }
    }

  check.deadline = monotonic_ms();
  if (check.deadline < 0)
    {
      return -EIO;
    }
  check.deadline += secure ? XIAOPAI_HTTPS_TIMEOUT_MS : XIAOPAI_HTTP_TIMEOUT_MS;
#ifdef CONFIG_XIAOPAI_HTTPSCHECK
  if (secure)
    {
      ret = xiaopai_tls_create(&tls, check.deadline);
      if (ret < 0)
        return ret;
    }
#endif
  buffer = malloc(HTTP_BUFFER_SIZE);
  if (buffer == NULL)
    {
#ifdef CONFIG_XIAOPAI_HTTPSCHECK
      xiaopai_tls_destroy(tls);
#endif
      return -ENOMEM;
    }
  webclient_set_defaults(&check.client);
  check.client.url = url;
  check.client.method = post != NULL ? "POST" : "GET";
  check.client.protocol_version = WEBCLIENT_PROTOCOL_VERSION_HTTP_1_1;
  check.client.flags = WEBCLIENT_FLAG_NON_BLOCKING;
  check.client.buffer = buffer;
  check.client.buflen = HTTP_BUFFER_SIZE;
  check.client.header_callback = receive_header;
  check.client.header_callback_arg = &check;
  check.client.sink_callback = receive_body;
  check.client.sink_callback_arg = &check;
  if (post != NULL)
    {
      check.client.headers = post->headers;
      check.client.nheaders = post->nheaders;
      if (post->source != NULL)
        {
          check.client.bodylen = post->body_length;
          check.client.body_callback = send_body;
          check.client.body_callback_arg = &check;
        }
      else
        webclient_set_static_body(&check.client, post->body, strlen(post->body));
    }
#ifdef CONFIG_XIAOPAI_HTTPSCHECK
  if (secure)
    {
      check.client.tls_ops = &g_xiaopai_tls_ops;
      check.client.tls_ctx = tls;
    }
#endif

  if (post != NULL)
    printf("HTTPS POST: CA/hostname/date required; no automatic retries\n");
  else if (secure)
    printf("HTTPS check v21: GET, 32 KiB limit, CA/hostname/date required\n");
  else
    printf("HTTP check v18: GET, 32 KiB body limit, no TLS\n");
  printf("Socket deadline=%d s; DNS uses system resolver timeouts\n", secure ? 60 : 30);
  for (;;)
    {
      struct webclient_poll_info info;
      struct pollfd fd = {0};
      int remaining;

      ret = time_left(&check);
      if (ret < 0)
        { webclient_abort(&check.client); break; }
      ret = webclient_perform(&check.client);
      if (ret != -EAGAIN)
        {
          break;
        }
      remaining = time_left(&check);
      if (remaining < 0)
        {
          ret = remaining;
          webclient_abort(&check.client);
          break;
        }
      ret = webclient_get_poll_info(&check.client, &info);
      if (ret < 0)
        {
          webclient_abort(&check.client);
          break;
        }
      fd.fd = info.fd;
      if (info.flags & WEBCLIENT_POLL_INFO_WANT_READ)
        {
          fd.events |= POLLIN;
          stage = "receive";
        }
      if (info.flags & WEBCLIENT_POLL_INFO_WANT_WRITE)
        {
          fd.events |= POLLOUT;
        }
      if (fd.fd < 0 || fd.events == 0)
        {
          ret = -EIO;
          webclient_abort(&check.client);
          break;
        }
      bool cancellable = post != NULL && post->cancelled != NULL;
      ret = poll(&fd, 1, cancellable && remaining > 100 ? 100 : remaining);
      if (ret == 0 && cancellable) continue;
      if (ret < 0 && errno == EINTR)
        {
          continue;
        }
      if (ret <= 0 || (fd.revents & POLLNVAL) != 0)
        {
          ret = ret < 0 ? -errno : (ret == 0 ? -ETIMEDOUT : -EBADF);
          webclient_abort(&check.client);
          break;
        }
      /* Let the client consume EOF/socket errors, including POLLHUP. */
    }

  explicit_bzero(buffer, HTTP_BUFFER_SIZE);
  free(buffer);
  if (post != NULL)
    post->status = check.client.http_status;
#ifdef CONFIG_XIAOPAI_HTTPSCHECK
  xiaopai_tls_report(tls);
  xiaopai_tls_destroy(tls);
#endif
  if (ret == 0 && time_left(&check) < 0)
    {
      ret = time_left(&check);
    }
  if (ret == 0 && check.client.http_status / 100 != 2)
    {
      ret = -EPROTO;
    }
  if (ret < 0)
    {
      printf("%s check failed: stage=%s status=%u body_bytes=%zu error=%d\n",
             label, check.headers_seen ? "HTTP response" : stage,
             check.client.http_status, check.bytes, -ret);
      return ret;
    }
  printf("%s check passed: status=%u body_bytes=%zu; %s\n",
         label, check.client.http_status, check.bytes,
         secure ? "TLS certificate verified" : "TCP/HTTP only");
  return 0;
}

int xiaopai_httpcheck(const char *url)
{
  return run_check(url, false, NULL);
}

#ifdef CONFIG_XIAOPAI_HTTPSCHECK
int xiaopai_httpscheck(const char *url)
{
  int ret = pthread_mutex_trylock(&g_https_lock);
  if (ret != 0)
    {
      printf("HTTPS check busy\n");
      return -ret;
    }
  ret = run_check(url, true, NULL);
  pthread_mutex_unlock(&g_https_lock);
  return ret;
}

int xiaopai_https_post(const char *url, struct xiaopai_http_post *post)
{
  int ret;
  if (post == NULL || ((post->body == NULL) == (post->source == NULL)) ||
      (post->source != NULL && (post->body_length == 0 ||
                               post->body_length > 1024 * 1024)) ||
      (post->sink == NULL && (post->response == NULL || post->capacity == 0 ||
                             post->capacity > HTTP_BODY_LIMIT + 1)) ||
      (post->sink != NULL && (post->response_limit == 0 ||
                             post->response_limit > 4 * 1024 * 1024)) ||
      (post->nheaders != 0 && post->headers == NULL))
    return -EINVAL;
  post->bytes = 0;
  post->status = 0;
  if (post->sink == NULL) post->response[0] = '\0';
  ret = pthread_mutex_trylock(&g_https_lock);
  if (ret != 0)
    return -ret;
  ret = run_check(url, true, post);
  pthread_mutex_unlock(&g_https_lock);
  return ret;
}
#endif
