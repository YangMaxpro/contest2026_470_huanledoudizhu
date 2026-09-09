/* SPDX-License-Identifier: Apache-2.0 */
#include <stddef.h>
#include <string.h>

/* Audited AHPL rb_node ABI: parent/color at 0, right at 4, left at 8.
 * The TLS deinit visitor frees its node, so neither child can be read after
 * invoking the visitor. The vendor LDR walker reads right after that free.
 */
static int walk(void *node, int (*visit)(void *, void *), void *arg)
{
  if (!node) return 0;
  void *left;
  void *right;
  memcpy(&right, (char *)node + sizeof(void *), sizeof(right));
  memcpy(&left, (char *)node + 2 * sizeof(void *), sizeof(left));
  int result = walk(left, visit, arg);
  if (result) return result;
  result = visit(node, arg);
  return result ? result : walk(right, visit, arg);
}

void ahpl_rb_traverse_ldr(void *root, int (*visit)(void *, void *), void *arg)
{
  void *node;
  memcpy(&node, root, sizeof(node));
  (void)walk(node, visit, arg);
}
