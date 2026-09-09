/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XIAOPAI_TLS_H
#define XIAOPAI_TLS_H
#include <stdint.h>
struct xiaopai_tls;
struct webclient_tls_ops;
extern const struct webclient_tls_ops g_xiaopai_tls_ops;
int xiaopai_tls_create(struct xiaopai_tls **out, int64_t deadline);
void xiaopai_tls_destroy(struct xiaopai_tls *tls);
void xiaopai_tls_report(const struct xiaopai_tls *tls);
#endif
