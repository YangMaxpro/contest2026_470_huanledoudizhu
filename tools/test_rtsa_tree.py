#!/usr/bin/env python3
"""Exercise AHPL in-order traversal with immediately freed nodes under ASan."""
import pathlib
import subprocess
import sys
import tempfile

source = pathlib.Path(sys.argv[1]).resolve()
test = r'''
#include <assert.h>
#include <stdlib.h>
#include "rtsa_tree.c"
struct node { struct node *parent, *right, *left; int value; };
static int values[8], count, stop;
static struct node *make(int v) {
  struct node *n = calloc(1, sizeof(*n)); assert(n); n->value = v; return n;
}
static int destroy(void *ptr, void *arg) {
  struct node *n = ptr; assert(arg == values);
  values[count++] = n->value; free(n); return 0;
}
static int inspect(void *ptr, void *arg) {
  struct node *n = ptr; assert(arg == values);
  values[count++] = n->value; return n->value == stop ? 7 : 0;
}
/* Reproduce the instruction order in the archived vendor walker. */
static int legacy_walk(struct node *n) {
  if (!n) return 0;
  int result = legacy_walk(n->left);
  if (result) return result;
  result = destroy(n, values);
  return result ? result : legacy_walk(n->right);
}
int main(int argc, char **argv) {
  (void)argv;
  if (argc > 1) { struct node *n = make(1); return legacy_walk(n); }
  struct node *root = NULL;
  ahpl_rb_traverse_ldr(&root, destroy, values); assert(count == 0);
  root = make(2); root->left = make(1); root->right = make(3);
  stop = 2; ahpl_rb_traverse_ldr(&root, inspect, values);
  assert(count == 2 && values[0] == 1 && values[1] == 2);
  count = 0; ahpl_rb_traverse_ldr(&root, destroy, values);
  assert(count == 3 && values[0] == 1 && values[1] == 2 && values[2] == 3);
}
'''
with tempfile.TemporaryDirectory(prefix="rtsa-tree-") as tmp:
    root = pathlib.Path(tmp)
    src, exe = root / "test.c", root / "test"
    src.write_text(test)
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-I" + str(source.parent), str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=15)
    legacy = subprocess.run([str(exe), "legacy"], capture_output=True, text=True, timeout=15)
    assert legacy.returncode != 0 and "heap-use-after-free" in legacy.stderr, legacy.stderr
print("PASS RTSA tree: legacy UAF reproduced; replacement passes empty, in-order, early stop and freeing callback")
