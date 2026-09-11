#!/usr/bin/env python3
"""Check the imported chip driver with fake MMIO and PWC transport."""
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "network"))
from test_audio_diag import stripped
from test_cp_random import run

stub = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <errno.h>
#include <inttypes.h>
#define CONFIG_BK7258_AUDIO 1
#define OK 0
#define auderr(...) ((void)0)
#define audinfo(...) ((void)0)
#define BK7258_AUD_BASE 0x47800000u
#define BK7258_SYSCTRL_BASE 0x44010000u
#define BK7258_SYS_CLKDIV1 (BK7258_SYSCTRL_BASE + 0x20u)
#define BK7258_IRQ_AUDIO 39
typedef int irqstate_t;
static unsigned votes, waits, writes, fifo_reads, fifo_writes;
static int transport_error;
static uint32_t regs[256], sysregs[256], fifo;
static int (*handler)(int, void *, void *);
static uint32_t getreg32(uint32_t addr)
{
  if(addr==BK7258_AUD_BASE+0x44)fifo_reads++;
  return addr>=BK7258_AUD_BASE ? regs[(addr-BK7258_AUD_BASE)/4]
                                : sysregs[(addr-BK7258_SYSCTRL_BASE)/4];
}
static void putreg32(uint32_t v,uint32_t addr)
{
  writes++;
  if(addr==BK7258_AUD_BASE+0x48){fifo_writes++;fifo=v;}
  if(addr>=BK7258_AUD_BASE) regs[(addr-BK7258_AUD_BASE)/4]=v;
  else sysregs[(addr-BK7258_SYSCTRL_BASE)/4]=v;
}
static void modifyreg32(uint32_t a,uint32_t c,uint32_t s)
{putreg32((getreg32(a)&~c)|s,a);}
static int enter_critical_section(void){return 0;}
static void leave_critical_section(int f){(void)f;}
static void up_udelay(int n){(void)n;}
static void nxsig_usleep(int n){(void)n;}
static int bk7258_mailbox_send_pwc(int c,uint32_t p1,uint32_t p2,int p3)
{assert((c==1 && p1==122 && p2<=1)||(c==2 && p1==30 && p2<=1));
 assert(p3==0); votes++;return transport_error;}
static int bk7258_mailbox_wait_pwc(int t){assert(t==500);waits++;return 0;}
static int irq_attach(int irq,int (*h)(int,void *,void *),void *arg)
{assert(irq==BK7258_IRQ_AUDIO && arg==NULL);handler=h;return 0;}
static void up_enable_irq(int irq){assert(irq==BK7258_IRQ_AUDIO);}
'''

test = r'''
int main(void)
{
  struct bk7258_aud_config cfg={.samplerate=16000,.clksrc=BK7258_AUD_CLK_XTAL,
    .dac_dig_gain=0x2d,.dac_ana_gain=0x0a,.adc_gain=0x2d};
  int16_t sample=-32768,out=0;
  assert(bk7258_aud_acquire(NULL)==-EINVAL);
  assert(bk7258_aud_acquire(&sample)==0);
  assert(bk7258_aud_acquire(&sample)==-EBUSY);
  bk7258_aud_release(&out);
  assert(bk7258_aud_acquire(&out)==-EBUSY);
  bk7258_aud_release(&sample);
  assert(bk7258_aud_acquire(&out)==0);
  bk7258_aud_release(&out);
  transport_error=-EBUSY;
  assert(bk7258_aud_initialize()==-EBUSY && waits==0 && writes==0);
  transport_error=0;
  assert(bk7258_aud_initialize()==-ENODEV && waits==4);
  regs[0]=0x12345678;
  assert(bk7258_aud_initialize()==0 && votes==7 && waits==6);
  assert(regs[2]==3 && handler!=NULL);
  assert(bk7258_aud_initialize()==0 && votes==7);
  assert(bk7258_aud_dac_setup(&cfg)==0);
  cfg.samplerate=24000;
  assert(bk7258_aud_dac_setup(&cfg)==0);
  assert(getreg32(BK7258_AUD_DAC_FRACMOD)==(BK7258_AUD_FRACMOD_48K<<1));
  assert(getreg32(BK7258_AUD_EXTEND_CFG)&BK7258_AUD_DAC_FRACMOD_MANUAL);
  cfg.samplerate=16000;
  assert(bk7258_aud_dac_setup(&cfg)==0);
  assert(!(getreg32(BK7258_AUD_EXTEND_CFG)&BK7258_AUD_DAC_FRACMOD_MANUAL));
  assert(bk7258_aud_adc_setup(&cfg)==0);
  assert(bk7258_aud_adc_threshold()==4);
  assert(((regs[0x28/4] & BK7258_AUD_DACL_RD_THRED_MASK) >>
          BK7258_AUD_DACL_RD_THRED_SHIFT)==16);
  assert((sysregs[(0x100+27*4)/4] & BK7258_ANA_MIC_EN)==0);
  assert(bk7258_aud_dac_write(&sample,1)==1 && fifo==0x80008000);
  regs[0x38/4]=BK7258_AUD_DACL_FIFO_FULL;
  assert(bk7258_aud_dac_write(&sample,1)==0 && fifo_writes==1);
  regs[0x38/4]=0; regs[0x44/4]=0xabcd0123;
  assert(bk7258_aud_adc_read(&out,1)==1 && out==0x123 && fifo_reads==1);
  regs[0x38/4]=BK7258_AUD_ADC_FIFO_EMPTY;
  assert(bk7258_aud_adc_read(&out,1)==0 && fifo_reads==1);
  bk7258_aud_tx_int_enable(true); bk7258_aud_rx_int_enable(true);
  regs[0x38/4]=BK7258_AUD_DACL_INT_FLAG|BK7258_AUD_ADC_INT_FLAG;
  handler(BK7258_IRQ_AUDIO,NULL,NULL);
  assert((regs[0x28/4]&(BK7258_AUD_DACL_INT_EN|BK7258_AUD_ADC_INT_EN))==0);
  sysregs[0xe8/4]=1u<<19;
  assert(bk7258_aud_adc_setup(&cfg)==-ETIMEDOUT);
  sysregs[0xe8/4]=0;
  bk7258_aud_adc_shutdown(); bk7258_aud_dac_shutdown();
  assert(!g_aud_adc_ready && !g_aud_dac_ready);
  assert((sysregs[(0x100+19*4)/4]&BK7258_ANA_MIC_EN)==0);
  assert((sysregs[(0x100+20*4)/4]&BK7258_ANA20_DACLEN)==0);
  puts("audio MMIO: PWC ordering/errors, reset, mono FIFO packing, IRQ masking,");
  puts("            analog timeout and partial-setup shutdown passed");
}
'''

if __name__ == '__main__':
    chip = pathlib.Path(sys.argv[1])
    run(stub + stripped(chip / 'hardware/bk7258_aud.h')
        + stripped(chip / 'include/bk7258_aud.h')
        + stripped(chip / 'bk7258_aud.c') + test)
