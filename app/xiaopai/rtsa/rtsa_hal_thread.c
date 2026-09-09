/* SPDX-License-Identifier: Apache-2.0 */
/* Replacement for the audited vendor HAL function in the experimental probe. */
#include <errno.h>
#include <stdint.h>
#include <string.h>

int rtsa_agora_create_thread(uint32_t *handle, uint8_t priority,
                             const char *name, void (*entry)(void *),
                             uint32_t stack_size, void *arg);

int k_os_thread_create(uint32_t *handle, void (*entry)(void *), void *context)
{
  const char *name;
  uint32_t stack_size;

  if (!handle) return -EINVAL;
  *handle = 0;
  if (!entry || !context) return -EINVAL;

  /* RTSA 1.9.5.7 thread.c.obj reads only the name pointer at context+0.
   * Pass the original context unchanged to its existing startup handshake. */
  memcpy(&name, context, sizeof(name));
  if (!name) return -EINVAL;
  if (strstr(name, "LTWP")) stack_size = 4096;
  else if (strstr(name, "RTCCB")) stack_size = 10240;
  else if (strstr(name, "IOT")) stack_size = 5120;
  else if (strstr(name, "IOT_CB")) stack_size = 3072;
  else stack_size = 12288;

  /* Unlike the vendor implementation, propagate failure: k_thread_create
   * then skips waiting for a nonexistent thread and destroys its handshake. */
  return rtsa_agora_create_thread(handle, 2, name, entry, stack_size, context);
}
