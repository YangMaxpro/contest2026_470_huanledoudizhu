/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XIAOPAI_HTTPCHECK_H
#define XIAOPAI_HTTPCHECK_H
#include <stddef.h>
#include <stdbool.h>
#include <sys/types.h>

struct xiaopai_http_post
{
  const char *body;
  const char *const *headers;
  unsigned int nheaders;
  char *response;
  size_t capacity;
  size_t bytes;
  unsigned int status;
  /* Optional bounded streaming I/O. Callbacks return negative errno.
   * source and body are mutually exclusive; sink bypasses response storage.
   * Cancellation is cooperative; DNS retains the system resolver timeout. */
  ssize_t (*source)(void *arg, char *buffer, size_t capacity);
  size_t body_length;
  int (*sink)(void *arg, const char *buffer, size_t length);
  size_t response_limit;
  bool (*cancelled)(void *arg);
  void *arg;
};

int xiaopai_httpcheck(const char *url);
int xiaopai_httpscheck(const char *url);
int xiaopai_https_post(const char *url, struct xiaopai_http_post *post);

#endif
