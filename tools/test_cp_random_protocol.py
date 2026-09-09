#!/usr/bin/env python3
"""Exercise the actual CP handler and AP random command wrapper with stubs."""
import pathlib
import sys

from test_cp_random import common, run


cp_stub = r'''
#define BK_CMD_OPENVELA_TRNG 0x213
struct bk_msg_hdr { unsigned cmd_id; unsigned len; };
static int fill_result, confirm_result, fills, confirms;
static unsigned char wire[40];
static int bk_fill_rand(void *p, size_t n)
{ assert(n == 32); fills++; memset(p, 0xa5, n); return fill_result; }
static int cif_bk_cmd_confirm(struct bk_msg_hdr *m, uint8_t *p, size_t n)
{ (void)m; assert(n == 40); confirms++; memcpy(wire, p, n); return confirm_result; }
'''
cp_main = r'''
int main(void)
{
  struct bk_msg_hdr msg = {0x213, 0};
  int32_t status;
  uint32_t version;
  assert(handler(&msg) == 0 && fills == 1 && confirms == 1);
  memcpy(&status, wire, 4); memcpy(&version, wire + 4, 4);
  assert(status == 0 && version == 1 && wire[8] == 0xa5);
  fill_result = -1;
  assert(handler(&msg) == 0);
  memcpy(&status, wire, 4); assert(status == -1);
  for (unsigned i = 8; i < 40; i++) assert(wire[i] == 0);
  msg.len = 1;
  assert(handler(&msg) == 0 && fills == 2 && confirms == 3);
  memcpy(&status, wire, 4); assert(status == -1);
  for (unsigned i = 8; i < 40; i++) assert(wire[i] == 0);
  confirm_result = -ENOMEM;
  assert(handler(&msg) == -ENOMEM);
  puts("CP random ABI: size, version, malformed request, fill/confirm failures passed");
}
'''
ap_stub = r'''
#define OK 0
static struct { bool initialized; } g_wifi;
static int transport_result, commands;
static uint16_t response_length = 40;
static int32_t response_status;
static uint32_t response_version = 1;
static int wifi_command(unsigned cmd, void *req, size_t n, void *out,
                        size_t cap, uint16_t *received)
{
  assert(cmd == 0x213 && req == NULL && n == 0 && cap == 40);
  commands++;
  memset(out, 0xa5, cap);
  memcpy(out, &response_status, 4);
  memcpy((char *)out + 4, &response_version, 4);
  *received = response_length;
  return transport_result;
}
'''
ap_main = r'''
int main(void)
{
  uint8_t out[32];
  memset(out, 0x55, sizeof(out));
  assert(bk7258_wifi_random_block(NULL, 32) == -EINVAL);
  assert(bk7258_wifi_random_block(out, 31) == -EINVAL);
  assert(bk7258_wifi_random_block(out, 32) == -ENODEV && commands == 0);
  g_wifi.initialized = true;
  transport_result = -ETIMEDOUT;
  assert(bk7258_wifi_random_block(out, 32) == -ETIMEDOUT);
  transport_result = 0;
  response_length = 39;
  assert(bk7258_wifi_random_block(out, 32) == -EPROTO);
  response_length = 41;
  assert(bk7258_wifi_random_block(out, 32) == -EPROTO);
  response_length = 40; response_version = 2;
  assert(bk7258_wifi_random_block(out, 32) == -EPROTO);
  response_version = 1; response_status = -1;
  assert(bk7258_wifi_random_block(out, 32) == -EIO);
  for (unsigned i = 0; i < 32; i++) assert(out[i] == 0x55);
  response_status = 0;
  assert(bk7258_wifi_random_block(out, 32) == 0);
  for (unsigned i = 0; i < 32; i++) assert(out[i] == 0xa5);
  puts("AP random ABI: invalid arguments, unavailable, timeout, length/version/status passed");
}
'''


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_cp_random_protocol.py CP_CIF_CNTRL AP_WIFI")
    cp = pathlib.Path(sys.argv[1]).read_text()
    start = cp.index("        case BK_CMD_OPENVELA_TRNG:")
    end = cp.index("        case BK_CMD_CONNECT:", start)
    run(common + cp_stub + "int handler(struct bk_msg_hdr *msg) {\n"
        "int ret = 0; switch (msg->cmd_id) {\n" + cp[start:end]
        + "default: return -EINVAL; } return ret; }\n" + cp_main)
    ap = pathlib.Path(sys.argv[2]).read_text()
    start = ap.index("int bk7258_wifi_random_block(")
    end = ap.index("\n#endif", start)
    run(common + ap_stub + ap[start:end] + ap_main)
