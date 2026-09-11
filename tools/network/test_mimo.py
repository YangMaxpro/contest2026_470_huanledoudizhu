#!/usr/bin/env python3
"""Host tests of actual MiMo C code with a stubbed HTTP transport; no real key."""
import pathlib
import subprocess
import sys
import tempfile

apps, app = map(pathlib.Path, sys.argv[1:3])
MAIN = r'''
#include <assert.h>
#include "xiaopai_mimo.c"
static int calls;
static int mode;
int xiaopai_https_post(const char *url, struct xiaopai_http_post *post)
{
  calls++;
  assert(!strcmp(url, "https://api.xiaomimimo.com/v1/chat/completions"));
  assert(!strcmp(post->headers[0], "api-key: sk-test-only-123"));
  cJSON *r = cJSON_Parse(post->body);
  assert(r);
  assert(!strcmp(cJSON_GetObjectItemCaseSensitive(r,"model")->valuestring,"mimo-v2.5"));
  assert(cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(r,"stream")));
  assert(cJSON_GetObjectItemCaseSensitive(r,"max_completion_tokens")->valueint == 256);
  assert(!strcmp(cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(r,"thinking"),"type")->valuestring,"disabled"));
  cJSON *user = cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(r,"messages"),1);
  assert(!strcmp(cJSON_GetObjectItemCaseSensitive(user,"content")->valuestring,"hello \"quoted\" \\ world"));
  cJSON_Delete(r);
  const char *reply = "{\"choices\":[{\"finish_reason\":\"stop\",\"message\":{\"content\":\"Hi!\"}}]}";
  if (mode == 1) reply = "{\"error\":\"do not print sk-test-only-123\"}";
  post->status = mode == 1 ? 401 : 200;
  strcpy(post->response,reply); post->bytes = strlen(reply);
  return mode == 1 ? -EPROTO : 0;
}
static int parse(const char *s) { return print_answer(s, strlen(s)); }
int main(int argc, char **argv)
{
  if (argc > 1 && !strcmp(argv[1],"key")) {
    int ret = read_key();
    if (!ret) assert(valid_key(g_key));
    return ret ? 1 : 0;
  }
  assert(valid_key("tp-other-endpoint"));
  assert(!valid_key("sk-abc\r\nX: injected"));
  assert(valid_key("sk-test-only-123"));
  assert(valid_key("tp-test-only-123"));
  assert(!valid_key(""));
  char *prompt[] = {"hello", "\"quoted\"", "\\", "world"};
  assert(xiaopai_mimo_ask(4,prompt) == -EACCES && calls == 0);
  strcpy(g_key,"sk-test-only-123");
  assert(!strcmp(mimo_url(), "https://api.xiaomimimo.com/v1/chat/completions"));
  strcpy(g_key,"tp-test-only-123");
  assert(!strcmp(mimo_url(), "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"));
  strcpy(g_key,"sk-test-only-123");
  char long_prompt[MIMO_PROMPT_MAX + 2];
  memset(long_prompt,'a',sizeof(long_prompt)-1); long_prompt[sizeof(long_prompt)-1]=0;
  char *long_args[] = {long_prompt};
  assert(xiaopai_mimo_ask(1,long_args) == -E2BIG && calls == 0);
  assert(xiaopai_mimo_ask(0,prompt) == -EINVAL && calls == 0);
  assert(xiaopai_mimo_ask(4,prompt) == 0 && calls == 1 && g_successes == 1);
  mode=1;
  assert(xiaopai_mimo_ask(4,prompt) < 0 && calls == 2 && g_successes == 1);
  assert(parse("{\"choices\":[{\"finish_reason\":\"stop\",\"message\":{\"content\":\"Hello \\u4f60\\u597d\"}}]}")==0);
  assert(parse("{\"choices\":[{\"finish_reason\":\"stop\",\"message\":{\"content\":\"\\u001b[31mred\"}}]}")==0);
  assert(parse("{\"choices\":[{\"finish_reason\":\"stop\",\"message\":{\"content\":\"sk-test-only-123\"}}]}")<0);
  const char *bad[] = {"", "<html>error</html>", "{}", "{\"choices\":[]}",
    "{\"choices\":[{\"finish_reason\":\"length\",\"message\":{\"content\":\"short\"}}]}",
    "{\"choices\":[{\"finish_reason\":\"stop\",\"message\":{\"content\":null}}]}",
    "{\"choices\":[{\"finish_reason\":\"tool_calls\",\"message\":{\"content\":\"execute\"}}]}",
    "{\"choices\":[{\"finish_reason\":\"stop\",\"message\":{\"content\":\"\"}}]}",
    "{\"choices\":[{\"finish_reason\":\"stop\",\"message\":{\"content\":\"ok\"}}]}junk"};
  for (unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++) assert(parse(bad[i])<0);
  assert(!json_bounded("[[[[[[[[[[[[[0]]]]]]]]]]]]]",27));
  assert(!json_bounded("{}\0junk",7));
  char *status[]={"status"}; assert(xiaopai_cloud(1,status)==0);
  char *invalid_model[]={"model","mimo-v2-flash"}; assert(xiaopai_cloud(2,invalid_model)<0);
  pthread_mutex_lock(&g_mimo_lock);
  assert(xiaopai_mimo_ask(4,prompt)<0 && calls==2);
  assert(xiaopai_cloud(1,status)<0);
  pthread_mutex_unlock(&g_mimo_lock);
  char *clear[]={"clear"}; assert(xiaopai_cloud(1,clear)==0 && g_key[0]==0);
  puts("PASS: MiMo request/schema/limits/auth/reflection/control filtering/concurrency/clear");
  return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="xiaopai-mimo-") as tmp:
    root = pathlib.Path(tmp)
    (root / "nuttx").mkdir()
    (root / "netutils").mkdir()
    (root / "nuttx/config.h").write_text("")
    (root / "netutils/cJSON.h").symlink_to((apps / "netutils/cjson/cJSON/cJSON.h").resolve())
    (root / "main.c").write_text(MAIN)
    binary = root / "test"
    subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-g",
                    "-fsanitize=address,undefined", "-I" + str(root), "-I" + str(app),
                    str(root / "main.c"), str(apps / "netutils/cjson/cJSON/cJSON.c"),
                    "-pthread", "-lm", "-o", str(binary)], check=True)
    result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=10)
    print(result.stdout)
    assert result.returncode == 0, result.stderr
    assert "sk-test-only-123" not in result.stdout
    assert "\x1b" not in result.stdout
    for key, success in [("sk-test-only-123\n", True), ("tp-test-only-123\n", True),
                         ("sk-" + "x" * 300 + "\n", False), ("\x03", False),
                         ("sk-test\x00junk\n", False), ("sk-abc\bZ\n", True)]:
        result = subprocess.run([str(binary), "key"], input=key, text=True,
                                capture_output=True, timeout=5)
        assert result.returncode == (0 if success else 1), (result.stdout, result.stderr)
        assert key.strip() not in result.stdout
    print("PASS: hidden key input, invalid/long/NUL/cancel/backspace; ASan/UBSan")
