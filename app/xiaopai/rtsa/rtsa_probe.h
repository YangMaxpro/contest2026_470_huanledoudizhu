/* SPDX-License-Identifier: Apache-2.0 */
#ifndef RTSA_PROBE_H
#define RTSA_PROBE_H

#define RTSA_STEP_IDLE 0
#define RTSA_STEP_PREFLIGHT 1
#define RTSA_STEP_INIT 2
#define RTSA_STEP_CREATE 3
#define RTSA_STEP_DESTROY 4
#define RTSA_STEP_FINI 5
#define RTSA_STEP_DONE 6
#define RTSA_STEP_QUEUED 7
#define RTSA_STEP_HOLD 8

/* Integer-only boundary between native and vendor short-enum units. */
void rtsa_probe_step(int step, int result);
void rtsa_probe_error(int error);
int rtsa_sdk_smoke(const char *app_id);
int rtsa_loopback_ready(void);
#endif
