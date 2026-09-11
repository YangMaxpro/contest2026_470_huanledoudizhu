#!/usr/bin/env python3
"""Exercise the real bounded audio controller with simulated FIFO/IRQ/time."""
import pathlib
import re
import subprocess
import sys
import tempfile


def stripped(path):
    return re.sub(r'^#include[^\n]*', '', pathlib.Path(path).read_text(), flags=re.M)


stub = r'''
#define CONFIG_BK7258_AUDIO 1
#define FAR
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <inttypes.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
typedef int mutex_t;
typedef int irqstate_t;
#define NXMUTEX_INITIALIZER 0
#define MSEC2TICK(x) (x)
#define TICK2MSEC(x) (x)
#define BK7258_AUD_ADC_FIFO_FULL (1u << 10)
#define BK7258_AUD_ADC_FIFO_EMPTY (1u << 14)
#define BK7258_AUD_DACL_FIFO_EMPTY (1u << 13)
#define CONFIG_USEC_PER_TICK 10000
static int locked, noirq, stuckirq, allocfail, setupfail, initfail, muted=1;
static int pa, txen, rxen, started, sleepfail, slept, pacycles;
static unsigned pushed, reads, statusbits;
static bool drain_empties, after_read, expect_zero;
static const void *owner;
static clock_t ticks;
static void (*txcb)(void *), (*rxcb)(void *);
static void *txarg, *rxarg;
static int nxmutex_trylock(mutex_t *m)
{(void)m; if(locked) return -EBUSY; locked=1; return 0;}
static void nxmutex_unlock(mutex_t *m) {(void)m; locked=0;}
static int enter_critical_section(void) {return 0;}
static void leave_critical_section(int f) {(void)f;}
static void *kmm_malloc(size_t n) {return allocfail ? NULL : malloc(n);}
#define kmm_free free
static void bk7258_board_audio_pa(bool on) {pa=on; if(on) pacycles++;}
static clock_t clock_systime_ticks(void) {return ticks;}
static int nxsig_usleep(unsigned usec)
{
  slept++;
  if(sleepfail && slept==sleepfail) return -EINTR;
  ticks += usec / 1000;
  if(!noirq && started)
    for(unsigned i=0;i<usec/2000;i++)
      {
        if(txen && txcb) txcb(txarg);
        if(rxen && rxcb) {after_read=false; rxcb(rxarg);}
      }
  return 0;
}
'''

drivers = r'''
int bk7258_aud_acquire(const void *value)
{if(!value)return -EINVAL; if(owner)return -EBUSY; owner=value; return 0;}
void bk7258_aud_release(const void *value) {if(value==owner)owner=NULL;}
int bk7258_aud_initialize(void) {return initfail;}
uint32_t bk7258_aud_read_id(void) {return 0x1234;}
int bk7258_aud_dac_setup(const struct bk7258_aud_config *c)
{assert(c->samplerate==16000 && c->dac_dig_gain==0x2d); return setupfail;}
int bk7258_aud_adc_setup(const struct bk7258_aud_config *c)
{assert(!c->capture_reference && c->mic_gain==0); return setupfail;}
void bk7258_aud_dac_shutdown(void) {started=0; muted=1;}
void bk7258_aud_adc_shutdown(void) {started=0;}
void bk7258_aud_dac_start(void) {started=1;}
void bk7258_aud_adc_start(void) {started=1;}
void bk7258_aud_dac_stop(void) {started=0;}
void bk7258_aud_adc_stop(void) {started=0;}
int bk7258_aud_dac_mute(bool mute) {muted=mute; return 0;}
void bk7258_aud_tx_int_enable(bool on) {txen=on;}
void bk7258_aud_rx_int_enable(bool on) {rxen=on;}
void bk7258_aud_set_tx_callback(bk7258_aud_xfer_cb_t cb, void *a)
{txcb=cb;txarg=a;}
void bk7258_aud_set_rx_callback(bk7258_aud_xfer_cb_t cb, void *a)
{rxcb=cb;rxarg=a;}
uint32_t bk7258_aud_adc_threshold(void) {return 4;}
uint32_t bk7258_aud_fifo_status(void)
{return drain_empties && after_read ? BK7258_AUD_ADC_FIFO_EMPTY : statusbits;}
unsigned bk7258_aud_dac_write(const int16_t *p, unsigned n)
{
  assert(n<=64); if(n>32)n=32;
  if(stuckirq)return 0;
  for(unsigned i=0;i<n;i++)assert(p[i]>=-1024 && p[i]<=1024);
  if(expect_zero)for(unsigned i=0;i<n;i++)assert(p[i]==0);
  pushed+=n; return n;
}
unsigned bk7258_aud_adc_read(int16_t *p, unsigned n)
{
  assert(n<=64); if(n>32)n=32;
  if(stuckirq)return 0;
  after_read=true;
  for(unsigned i=0;i<n;i++)
    {p[i]=reads<3200 ? 32767 : ((reads&1) ? -100 : 100); reads++;}
  return n;
}
'''

test = r'''
static void clean(void)
{
  assert(!locked && !pa && !txen && !rxen && !started);
  assert(txcb==NULL && rxcb==NULL && muted);
  assert(owner==NULL);
}
int main(void)
{
  struct bk7258_audio_report_s r;
  int16_t copy[BK7258_AUDIO_CLIP_SAMPLES];
  assert(bk7258_audio_diag(BK7258_AUDIO_STATUS,NULL)==-EINVAL);
  assert(bk7258_audio_diag(99,&r)==-EINVAL);
  assert(bk7258_audio_diag(BK7258_AUDIO_PLAY,&r)==-ENODATA); clean();
  assert(bk7258_audio_copy(NULL,16000)==-EINVAL);
  assert(bk7258_audio_copy(copy,15999)==-EINVAL);
  assert(bk7258_audio_copy(copy,16000)==-ENODATA); clean();
  assert(bk7258_audio_replay(4,&r)==-ENODATA); clean();
  assert(bk7258_audio_replay(4,NULL)==-EINVAL);
  const unsigned invalid[] = {0, 3, 5, 16, UINT32_MAX};
  for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++)
    {
      assert(bk7258_audio_replay(invalid[i],&r)==-EINVAL);
      assert(r.samples==0 && !pacycles); clean();
    }
  char *badargs[] = {"xiaopai", "audio", "play", "0"};
  assert(xiaopai_audio(4,badargs)==-EINVAL && !pacycles); clean();
  badargs[3]="";
  assert(xiaopai_audio(4,badargs)==-EINVAL && !pacycles); clean();
  badargs[3]="4junk";
  assert(xiaopai_audio(4,badargs)==-EINVAL && !pacycles); clean();
  badargs[2]="record"; badargs[3]="4";
  assert(xiaopai_audio(4,badargs)==-EINVAL && !pacycles); clean();
  locked=1;
  assert(bk7258_audio_diag(BK7258_AUDIO_TONE,&r)==-EBUSY);
  assert(bk7258_audio_copy(copy,16000)==-EBUSY);
  locked=0;
  owner=&r;
  assert(bk7258_audio_diag(BK7258_AUDIO_TONE,&r)==-EBUSY && !pacycles);
  assert(owner==&r && !locked);
  owner=NULL;
  assert(bk7258_audio_diag(BK7258_AUDIO_STATUS,&r)==0 && !pacycles); clean();
  assert(audio_sqrt(0)==0 && audio_sqrt(10000)==100);
  assert(audio_sqrt(1073741824)==32768);
  for(unsigned i=0;i<DIAG_RATE;i++)
    assert(abs(audio_sample(i,true,0,8))<=320);
  assert(audio_sample(0,true,0,8)==0 && audio_sample(DIAG_RATE-1,true,0,8)==0);
  assert(bk7258_audio_diag(BK7258_AUDIO_TONE,&r)==0);
  assert(r.samples==16000 && r.interrupts>0 && pacycles==1); clean();
  assert(r.raw_samples==16000 && r.elapsed_ms==1000 && r.max_batch==32);
  allocfail=1;
  assert(bk7258_audio_diag(BK7258_AUDIO_RECORD,&r)==-ENOMEM); clean();
  allocfail=0;
  assert(bk7258_audio_diag(BK7258_AUDIO_RECORD,&r)==0); clean();
  assert(r.samples==16000 && r.recorded==16000);
  assert(r.peak==100 && r.rms==100 && r.dc==0 && r.clipped==0);
  assert(reads==19200 && pacycles==1);
  assert(r.raw_samples==19200 && r.elapsed_ms==1200 && r.adc_threshold==4);
  assert(r.max_irq_gap_ms==10 && r.max_batch==32);
  assert(bk7258_audio_copy(copy,16000)==16000); clean();
  assert(memcmp(copy,g_clip,sizeof(copy))==0);
  char *dumpargs[]={"xiaopai","audio","dump"};
  assert(xiaopai_audio(3,dumpargs)==0); clean();
  expect_zero=true;
  assert(bk7258_audio_diag(BK7258_AUDIO_SILENCE,&r)==0); clean();
  assert(r.samples==16000 && r.recorded==16000);
  assert(memcmp(copy,g_clip,sizeof(copy))==0);
  expect_zero=false;
  assert(bk7258_audio_diag(BK7258_AUDIO_PLAY,&r)==0); clean();
  assert(g_transfer.replay_divisor==8);
  for(unsigned divisor=8;divisor>0;divisor/=2)
    {
      assert(audio_sample(1000,false,0,divisor)==100/(int)divisor);
      assert(audio_sample(1001,false,0,divisor)==-100/(int)divisor);
      assert(audio_sample(1000,false,20,divisor)==80/(int)divisor);
      assert(audio_sample(0,false,0,divisor)==0);
      assert(audio_sample(DIAG_RATE-1,false,0,divisor)==0);
      assert(bk7258_audio_replay(divisor,&r)==0); clean();
      assert(g_transfer.replay_divisor==divisor && r.samples==16000);
    }
  char *playargs[] = {"xiaopai", "audio", "play", "4"};
  assert(xiaopai_audio(4,playargs)==0); clean();
  assert(g_transfer.replay_divisor==4);
  assert(xiaopai_audio(3,playargs)==0); clean();
  assert(g_transfer.replay_divisor==8);
  for(unsigned i=0;i<DIAG_RATE;i++)g_clip[i]=(i&1)?-32768:32767;
  for(unsigned divisor=8;divisor>0;divisor/=2)
    for(unsigned i=0;i<DIAG_RATE;i++)
      assert(abs(audio_sample(i,false,0,divisor))<=1024);
  memset(&r,0,sizeof(r)); audio_statistics(&r);
  assert(r.peak==32768 && r.clipped==16000);
  assert(bk7258_audio_diag(BK7258_AUDIO_CLEAR,&r)==0 && !g_clip); clean();
  assert(bk7258_audio_copy(copy,16000)==-ENODATA); clean();
  noirq=1;
  assert(bk7258_audio_diag(BK7258_AUDIO_RECORD,&r)==-ETIMEDOUT); clean();
  assert(g_recorded==0);
  assert(r.elapsed_ms==3000 && r.raw_samples==0);
  for(unsigned i=0;i<DIAG_RATE;i++)assert(g_clip[i]==0);
  noirq=0;
  stuckirq=1;
  assert(bk7258_audio_diag(BK7258_AUDIO_RECORD,&r)==-EIO); clean();
  assert(r.interrupts==4);
  assert(r.max_batch==0 && r.raw_samples==0);
  assert(bk7258_audio_diag(BK7258_AUDIO_TONE,&r)==-EIO); clean();
  assert(bk7258_audio_diag(BK7258_AUDIO_SILENCE,&r)==-EIO); clean();
  stuckirq=0;
  setupfail=-EIO;
  assert(bk7258_audio_diag(BK7258_AUDIO_TONE,&r)==-EIO); clean();
  assert(bk7258_audio_diag(BK7258_AUDIO_RECORD,&r)==-EIO); clean();
  setupfail=0;
  slept=0; sleepfail=2;
  assert(bk7258_audio_diag(BK7258_AUDIO_TONE,&r)==-EINTR); clean();
  sleepfail=0; statusbits=BK7258_AUD_ADC_FIFO_FULL;
  assert(bk7258_audio_diag(BK7258_AUDIO_RECORD,&r)==0 && r.fifo_faults>0); clean();
  assert(r.full_after==r.interrupts && r.empty_after==0);
  drain_empties=true;
  assert(bk7258_audio_diag(BK7258_AUDIO_RECORD,&r)==0); clean();
  assert(r.full_after==0 && r.empty_after==r.interrupts);
  assert(r.status_before_or==BK7258_AUD_ADC_FIFO_FULL);
  assert(r.status_after_or==BK7258_AUD_ADC_FIFO_EMPTY);
  assert(r.fifo_faults==r.interrupts);
  assert(bk7258_audio_diag(BK7258_AUDIO_STATUS,&r)==0 && r.adc_threshold==4);
  assert(bk7258_audio_diag(BK7258_AUDIO_CLEAR,&r)==0); clean();
  assert(bk7258_audio_diag(BK7258_AUDIO_STATUS,&r)==0 && r.raw_samples==0);
  puts("audio: tone bounds, ramps, ADC settling/stats, replay/clamp, clear,");
  puts("       busy, no recording, allocation/setup failure, timeout and interruption passed");
  puts("v24: transfer timing, raw counts, ADC threshold, before/after flags and status passed");
  puts("v25: replay divisors, default level, DC, ramps, clamp and CLI validation passed");
  puts("v26: zero PCM, snapshot validation/exclusion, recording preservation and dump passed");
}
'''

if __name__ == '__main__':
    chip = pathlib.Path(sys.argv[1])
    code = (stub + stripped(chip.parents[3] / 'libs/libc/misc/lib_crc32.c')
            + stripped(chip / 'include/bk7258_aud.h')
            + stripped(chip / 'include/bk7258_audio_diag.h') + drivers
            + stripped(chip / 'bk7258_audio_diag.c')
            + stripped(pathlib.Path(__file__).resolve().parents[1]
                       / 'app/xiaopai/xiaopai_audio.c') + test)
    with tempfile.TemporaryDirectory(prefix='xiaopai-audio-') as tmp:
        path = pathlib.Path(tmp)
        (path / 'test.c').write_text(code)
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-g', str(path / 'test.c'),
                        '-o', str(path / 'test')], check=True)
        result = subprocess.run([str(path / 'test')], check=True,
                                capture_output=True, text=True)
        from decode_audio_dump import decode
        import struct
        captures = decode(result.stdout)
        assert captures == [struct.pack('<16000h', *([100, -100] * 8000))]
        print('\n'.join(line for line in result.stdout.splitlines()
                        if not line.startswith('PCM16 ')))
        print('v26: actual C exporter/CRC roundtrip through host decoder passed')
