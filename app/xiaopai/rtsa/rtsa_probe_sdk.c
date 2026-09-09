/* SPDX-License-Identifier: Apache-2.0 */
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include "agora_rtc_api.h"
#include "rtsa_probe.h"

_Static_assert(offsetof(rtc_service_option_t, license_value) == 84,
               "RTSA 1.9.5.7 service-option ABI mismatch");

static void on_error(connection_id_t connection, int code, const char *message)
{
  (void)connection;
  (void)message;
  rtsa_probe_error(code);
}

/* Retained for the whole SDK lifetime, including asynchronous callbacks. */
static agora_rtc_event_handler_t g_events = {.on_error = on_error};
static rtc_service_option_t g_options;

int rtsa_sdk_smoke(const char *app_id)
{
  connection_id_t connection;
  int result;
  int cleanup;
  memset(&g_options, 0, sizeof(g_options));
  g_options.area_code = AREA_CODE_GLOB;
  g_options.log_cfg.log_disable = true;
  g_options.log_cfg.log_disable_desensitize = false;
  rtsa_probe_step(RTSA_STEP_INIT, 0);
  result = agora_rtc_init(app_id, &g_events, &g_options);
  if (result) return result;

  rtsa_probe_step(RTSA_STEP_CREATE, 0);
  result = agora_rtc_create_connection(&connection);
  if (!result)
    {
      rtsa_probe_step(RTSA_STEP_DESTROY, 0);
      result = agora_rtc_destroy_connection(connection);
    }
  rtsa_probe_step(RTSA_STEP_HOLD, result);
  rtsa_probe_step(RTSA_STEP_FINI, result);
  cleanup = agora_rtc_fini();
  return result ? result : cleanup;
}
