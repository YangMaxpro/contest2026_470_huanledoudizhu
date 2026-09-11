#!/usr/bin/env python3
"""Real voice/MiMo C with fake PCM, scheduler and cloud; no network or keys."""
import pathlib
import subprocess
import sys
import tempfile

apps, app, chip = map(pathlib.Path, sys.argv[1:4])
MAIN = r'''
#include <assert.h>
#include <sched.h>
int task_create(const char *, int, int, int (*)(int,char **), char **);
int task_setcancelstate(int, int *);
#define TASK_CANCEL_DISABLE 1
#include "xiaopai_mimo.c"
#include "xiaopai_voice.c"
static bool active, capturing;
static unsigned starts, stops, calls, stage_calls, read_count, written, faults;
static int mode;
static unsigned test_seconds=1;
static size_t recording_size;
void *bk7258_psram_malloc(size_t size)
{ assert(!recording_size); if(mode==11)return NULL; recording_size=size; return malloc(size); }
void bk7258_psram_free(void *ptr)
{
  assert(ptr && recording_size);
  for(size_t i=0;i<recording_size;i++)assert(((unsigned char *)ptr)[i]==0);
  recording_size=0; free(ptr);
}
static int (*pending_worker)(int,char **);
int task_create(const char *name,int priority,int stack,int (*entry)(int,char **),char **args)
{
  assert(!strcmp(name,"xiaopai_voice") && priority==100 && stack==16384 && !args);
  if(mode==10) { errno=ENOMEM; return -1; }
  pending_worker=entry; return 100;
}
int task_setcancelstate(int state,int *old) { assert(state==1 && !old); return 0; }
int bk7258_pcm_start_rate(bool capture,uint32_t rate,uint32_t *session)
{
  assert(!active && rate==(capture?16000:24000));
  active=true; capturing=capture; *session=++starts; return 0;
}
int bk7258_pcm_start(bool capture,uint32_t *session)
{ return bk7258_pcm_start_rate(capture,16000,session); }
int bk7258_pcm_read(uint32_t session,int16_t *p,uint32_t count)
{
  assert(active && capturing && session && count<=320);
  if(mode==3) return -EIO;
  if(mode==4 && read_count>1000)faults=1;
  if(mode==12 && read_count>1000)g_cancel=true;
  if(count>73) count=73;
  for(unsigned i=0;i<count;i++)p[i]=(int16_t)((read_count++ % 1000)-500);
  return count;
}
int bk7258_pcm_write(uint32_t session,const int16_t *p,uint32_t count)
{
  assert(active && !capturing && session && count);
  if(mode==8) return -EIO;
  if(count>17) count=17;
  for(unsigned i=0;i<count;i++) { assert(p[i]==1000); written++; }
  return count;
}
int bk7258_pcm_status(uint32_t session,struct bk7258_pcm_status_s *status)
{
  assert(active && session); memset(status,0,sizeof(*status));
  status->running=true; status->capture=capturing;
  status->dropped_samples=faults; return 0;
}
int bk7258_pcm_stop(uint32_t session)
{ assert(active && session); active=false; stops++; return 0; }
int bk7258_pcm_drain(uint32_t session,unsigned timeout)
{ assert(active && !capturing && session && timeout==2000); return mode==9?-ETIMEDOUT:0; }

static int feed(struct voice_turn *t,const char *s,size_t split)
{
  size_t size=strlen(s);
  for(size_t i=0;i<size;) {
    size_t n=size-i; if(n>split)n=split;
    int ret=tts_sink(t,s+i,n); if(ret<0)return ret; i+=n;
  }
  return 0;
}
static void answer(struct xiaopai_http_post *post,const char *text)
{
  int n=snprintf(post->response,post->capacity,
      "{\"choices\":[{\"finish_reason\":\"stop\",\"message\":{\"content\":\"%s\"}}]}",text);
  assert(n>0 && (size_t)n<post->capacity); post->bytes=n; post->status=200;
}
int xiaopai_https_post(const char *url,struct xiaopai_http_post *post)
{
  assert(!strcmp(url,"https://api.xiaomimimo.com/v1/chat/completions"));
  assert(!strcmp(post->headers[0],"api-key: sk-fixture-only"));
  calls++; stage_calls++;
  if(mode==1)return -EACCES;
  if(post->cancelled && post->cancelled(post->arg))return -ECANCELED;
  if(post->source) {
    assert(stage_calls==1 && !post->body);
    char *body=malloc(post->body_length+1); size_t used=0;
    while(used<post->body_length) {
      size_t cap=(used%1024)+1;
      if(cap>post->body_length-used) cap=post->body_length-used;
      if(mode==2 && used>200)g_cancel=true;
      if(used>1024)assert(!active); /* Network stalls cannot keep MIC on. */
      if(mode==13 && used>1024)usleep(1000);
      ssize_t n=post->source(post->arg,body+used,cap);
      if(n<0) { free(body); return n; }
      assert(n>0 && (size_t)n<=cap); used+=n;
    }
    assert(!active); body[used]=0;
    cJSON *j=cJSON_Parse(body); assert(j);
    assert(!strcmp(cJSON_GetObjectItem(j,"model")->valuestring,"mimo-v2.5-asr"));
    cJSON *msg=cJSON_GetArrayItem(cJSON_GetObjectItem(j,"messages"),0);
    cJSON *item=cJSON_GetArrayItem(cJSON_GetObjectItem(msg,"content"),0);
    const char *data=cJSON_GetObjectItem(cJSON_GetObjectItem(item,"input_audio"),"data")->valuestring;
    assert(!strncmp(data,"data:audio/wav;base64,",22)); data+=22;
    size_t raw_size=44+test_seconds*32000; unsigned char *raw=malloc(raw_size); size_t n;
    assert(raw);
    assert(mbedtls_base64_decode(raw,raw_size,&n,(const unsigned char *)data,strlen(data))==0);
    assert(n==raw_size && !memcmp(raw,"RIFF",4) && !memcmp(raw+8,"WAVEfmt ",8));
    assert(raw[24]==0x80 && raw[25]==0x3e);
    assert(((unsigned)raw[40] | ((unsigned)raw[41]<<8) | ((unsigned)raw[42]<<16))==test_seconds*32000);
    assert(read_count==test_seconds*16000);
    for(unsigned i=0;i<test_seconds*16000;i++) {
      int16_t expected=(int16_t)((i%1000)-500);
      assert(raw[44+2*i]==((uint16_t)expected&255));
      assert(raw[45+2*i]==((uint16_t)expected>>8));
    }
    free(raw); cJSON_Delete(j); free(body); answer(post,"hello"); return 0;
  }
  cJSON *j=cJSON_Parse(post->body); assert(j);
  const char *model=cJSON_GetObjectItem(j,"model")->valuestring;
  if(!strcmp(model,"mimo-v2.5")) {
    assert(stage_calls==2);
    cJSON *msg=cJSON_GetArrayItem(cJSON_GetObjectItem(j,"messages"),1);
    assert(!strcmp(cJSON_GetObjectItem(msg,"content")->valuestring,"hello"));
    cJSON_Delete(j); if(mode==5)return -EPROTO; answer(post,"Hello friend"); return 0;
  }
  assert(stage_calls==3 && !strcmp(model,"mimo-v2.5-tts"));
  assert(cJSON_IsTrue(cJSON_GetObjectItem(j,"stream")));
  cJSON *msg=cJSON_GetArrayItem(cJSON_GetObjectItem(j,"messages"),0);
  assert(!strcmp(cJSON_GetObjectItem(msg,"role")->valuestring,"assistant"));
  assert(!strcmp(cJSON_GetObjectItem(msg,"content")->valuestring,"Hello friend"));
  assert(!strcmp(cJSON_GetObjectItem(cJSON_GetObjectItem(j,"audio"),"format")->valuestring,"pcm16"));
  cJSON_Delete(j);
  unsigned char samples[1200]; char encoded[1601]; size_t n;
  for(unsigned i=0;i<sizeof(samples);i+=2) { samples[i]=0x40; samples[i+1]=0x1f; }
  assert(!mbedtls_base64_encode((unsigned char *)encoded,sizeof(encoded),&n,samples,sizeof(samples)));
  char event[2048];
  snprintf(event,sizeof(event),": keepalive\r\ndata: {\"choices\":[{\"delta\":{\"audio\":{\"data\":\"%s\"}},\"finish_reason\":null}]}\r\n\r\n",encoded);
  struct voice_turn *t=post->arg;
  int ret=feed(t,event,7); if(ret<0)return ret;
  ret=feed(t,"data: {\"choices\":[{\"delta\":{},\"finish_reason\":\"stop\"}]}\n\n",1);
  if(ret<0)return ret;
  if(mode==6)return 0;
  if(mode==7)g_cancel=true;
  return feed(t,"data: [DONE]\n\n",3);
}
static void run(int m,int expected)
{
  mode=m; stage_calls=0; read_count=0; written=0; faults=0;
  unsigned previous=g_completed;
  char duration[4]; snprintf(duration,sizeof(duration),"%u",test_seconds);
  char *args[]={"start",duration};
  assert(xiaopai_voice(2,args)==0 && g_running);
  assert(xiaopai_voice(2,args)==-EBUSY);
  assert(pending_worker(0,NULL)==(expected==0?0:1));
  assert(!g_running && !g_pending && !active && starts==stops && !recording_size);
  assert(g_result==expected);
  assert(g_completed==previous+(expected==0));
  if(expected==0)assert(written==600 && g_played==600);
  assert(pthread_mutex_trylock(&g_mimo_lock)==0); pthread_mutex_unlock(&g_mimo_lock);
}
int main(void)
{
  char *args[]={"start","1"};
  assert(xiaopai_voice(0,NULL)==-EINVAL);
  assert(xiaopai_voice(2,args)==-EACCES && calls==0 && starts==0);
  strcpy(g_key,"sk-fixture-only");
  char *bad[]={"start","11"}; assert(xiaopai_voice(2,bad)==-EINVAL);
  bad[1]="-1"; assert(xiaopai_voice(2,bad)==-EINVAL);
  run(0,0); run(1,-EACCES); run(2,-ECANCELED); run(3,-EIO);
  run(4,-EOVERFLOW); run(5,-EPROTO); run(6,-EPROTO);
  run(7,-ECANCELED); run(8,-EIO); run(9,-ETIMEDOUT);
  run(11,-ENOMEM); run(12,-ECANCELED); run(13,0);
  test_seconds=3; run(0,0); test_seconds=10; run(0,0); test_seconds=1;
  mode=10; assert(xiaopai_voice(2,args)==-ENOMEM && !g_pending && !g_running);
  mode=0;
  struct voice_turn t={0}; t.deadline=voice_now()+60000;
  t.event=calloc(1,VOICE_EVENT_MAX+1); assert(t.event); g_cancel=false;
  const char *malformed[]={"data: [DONE]\n\n", "data: {}\n\n",
    "data: {\"choices\":[{\"delta\":{},\"finish_reason\":\"length\"}]}\n\n",
    "data: {\"choices\":[{\"delta\":{\"audio\":{\"data\":\"!!!=\"}}}]}\n\n"};
  for(unsigned i=0;i<sizeof(malformed)/sizeof(*malformed);i++) {
    assert(feed(&t,malformed[i],1)<0); t.event_size=t.line_size=0; t.had_data=false;
  }
  assert(play_base64(&t,"AA==")==-EPROTO);
  assert(play_base64(&t,"AA=A")==-EPROTO);
  assert(play_base64(&t,"")==-EPROTO);
  t.event_size=VOICE_EVENT_MAX; assert(event_char(&t,'x')==-EFBIG); t.event_size=0;
  assert(feed(&t,"data: {\n",2)==0);
  assert(feed(&t,"data: \"choices\":[]}\n\n",3)==0);
  assert(tts_sink(&t,"\0",1)==-EPROTO);
  free(t.event);
  puts("PASS voice: WAV/base64, partial capture/TX, ASR/model/TTS schemas, SSE splits,");
  puts("bounds, malformed/truncated streams, cancellation, overrun, errors and cleanup");
}
'''
with tempfile.TemporaryDirectory(prefix="xiaopai-voice-") as tmp:
    root = pathlib.Path(tmp)
    (root / "nuttx").mkdir()
    (root / "arch/chip").mkdir(parents=True)
    (root / "netutils").mkdir()
    (root / "nuttx/config.h").write_text("#define CONFIG_XIAOPAI_VOICE 1\n")
    (root / "netutils/cJSON.h").symlink_to((apps / "netutils/cjson/cJSON/cJSON.h").resolve())
    (root / "arch/chip/bk7258_pcm.h").symlink_to((chip / "include/bk7258_pcm.h").resolve())
    (root / "arch/chip/bk7258_psram.h").symlink_to((chip / "include/bk7258_psram.h").resolve())
    (root / "main.c").write_text(MAIN)
    (root / "base64_config.h").write_text("#define MBEDTLS_BASE64_C\n")
    binary = root / "test"
    mbed = apps / "crypto/mbedtls/mbedtls"
    subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-g",
                    "-fsanitize=address,undefined", '-DMBEDTLS_CONFIG_FILE="base64_config.h"',
                    "-I" + str(root), "-I" + str(app), "-I" + str(mbed / "include"),
                    str(root / "main.c"), str(apps / "netutils/cjson/cJSON/cJSON.c"),
                    str(mbed / "library/base64.c"), str(mbed / "library/constant_time.c"),
                    "-pthread", "-lm", "-o", str(binary)], check=True)
    result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=20)
    print(result.stdout)
    assert result.returncode == 0, result.stderr
    assert "sk-fixture-only" not in result.stdout
