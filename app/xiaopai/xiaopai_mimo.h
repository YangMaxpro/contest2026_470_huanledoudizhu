/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XIAOPAI_MIMO_H
#define XIAOPAI_MIMO_H
#include <stdbool.h>
#include <stddef.h>
struct xiaopai_http_post;
int xiaopai_cloud(int argc, char **argv);
int xiaopai_mimo_ask(int argc, char **argv);
/* Internal voice worker API: begin/end on the same thread; every function
 * below requires that reservation. Never put credentials in caller buffers. */
int xiaopai_mimo_begin(void);
bool xiaopai_mimo_json_bounded(const char *data, size_t size);
void xiaopai_mimo_end(void);
int xiaopai_mimo_post(struct xiaopai_http_post *post);
int xiaopai_mimo_extract(const char *data, size_t n, char *text, size_t capacity);
int xiaopai_mimo_reply(const char *prompt, char *reply, size_t capacity,
                       bool (*cancelled)(void *), void *arg);
#endif
