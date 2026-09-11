#!/usr/bin/env python3
"""Exercise real PCM transport with fake FIFO/time; no hardware access."""
import pathlib
import subprocess
import sys
import tempfile
from test_audio_diag import stub, drivers, stripped

test = r'''
static void clean(void)
{
  assert(!locked && !pa && !txen && !rxen && !started && owner==NULL);
  assert(txcb==NULL && rxcb==NULL && !g_pcm.active);
  for(unsigned i=0;i<BK7258_PCM_RING_SAMPLES;i++)assert(g_pcm.ring[i]==0);
}
int main(void)
{
  (void)kmm_malloc; /* Shared diagnostic stubs include an unused allocator. */
  uint32_t session, stale, other;
  struct bk7258_pcm_status_s s;
  int16_t block[320];
  assert(bk7258_pcm_start(true,NULL)==-EINVAL);
  assert(bk7258_pcm_start_rate(true,24000,&session)==-EINVAL && session==0);
  assert(bk7258_pcm_start_rate(false,44100,&session)==-EINVAL && session==0);
  expected_rate=24000;
  assert(bk7258_pcm_start_rate(false,24000,&session)==0 && session!=0);
  assert(bk7258_pcm_stop(session)==0); clean();
  expected_rate=16000;
  assert(bk7258_pcm_read(0,block,320)==-EBADF);
  assert(bk7258_pcm_write(0,NULL,320)==-EINVAL);
  owner=&s;
  assert(bk7258_pcm_start(true,&session)==-EBUSY && session==0 && !pa);
  owner=NULL;
  setupfail=-EIO;
  assert(bk7258_pcm_start(true,&session)==-EIO && session==0); clean();
  setupfail=0; initfail=-ENODEV;
  assert(bk7258_pcm_start(false,&session)==-ENODEV); clean();
  initfail=0;
  slept=0; sleepfail=1;
  assert(bk7258_pcm_start(false,&session)==-EINTR); clean();
  sleepfail=0;
  assert(bk7258_pcm_start(true,&session)==0 && session!=0 && !pa);
  assert(bk7258_pcm_start(false,&other)==-EBUSY && other==0);
  assert(bk7258_pcm_write(session,block,320)==-EPERM);
  assert(bk7258_pcm_drain(session,100)==-EPERM);
  assert(bk7258_pcm_read(session,block,320)==-EAGAIN);
  nxsig_usleep(200000);
  assert(bk7258_pcm_read(session,block,320)==-EAGAIN);
  for(unsigned frame=0;frame<300;frame++)
    {
      nxsig_usleep(20000);
      assert(bk7258_pcm_read(session,block,320)==320);
      for(unsigned i=0;i<320;i++)assert(block[i]==((i&1)?-100:100));
    }
  assert(bk7258_pcm_status(session,&s)==0 && s.running && s.capture);
  assert(s.fifo_samples==99200 && s.buffered==0 && s.dropped_samples==0);
  nxsig_usleep(400000);
  assert(bk7258_pcm_status(session,&s)==0);
  assert(s.buffered==4096 && s.dropped_samples==2304);
  stale=session;
  assert(bk7258_pcm_stop(session)==0); clean();
  assert(bk7258_pcm_stop(stale)==-EBADF);
  assert(bk7258_pcm_start(false,&session)==0 && session!=stale && pa);
  assert(bk7258_pcm_status(stale,&s)==-EBADF);
  assert(bk7258_pcm_read(session,block,320)==-EPERM);
  expect_zero=true; nxsig_usleep(20000); expect_zero=false;
  assert(bk7258_pcm_status(session,&s)==0 && s.silence_samples==320);
  for(unsigned i=0;i<320;i++)block[i]=(i&1)?-32768:32767;
  assert(bk7258_pcm_write(session,block,320)==320);
  assert(g_pcm.ring[0]==0 && g_pcm.ring[1]==-6);
  assert(g_pcm.ring[160]==1024 && g_pcm.ring[161]==-1024);
  for(unsigned i=0;i<300;i++)
    {
      nxsig_usleep(20000);
      assert(bk7258_pcm_write(session,block,320)==320);
    }
  assert(bk7258_pcm_status(session,&s)==0 && s.buffered==320);
  assert(s.limited_samples==301*320);
  while(bk7258_pcm_write(session,block,320)>0){}
  assert(bk7258_pcm_write(session,block,320)==-EAGAIN);
  noirq=1;
  assert(bk7258_pcm_drain(session,30)==-ETIMEDOUT);
  assert(bk7258_pcm_write(session,block,320)==-EPIPE);
  noirq=0; statusbits=BK7258_AUD_DACL_FIFO_EMPTY;
  assert(bk7258_pcm_drain(session,1000)==0 && !txen);
  assert(bk7258_pcm_drain(session,0)==-EINVAL);
  assert(bk7258_pcm_drain(session,2001)==-EINVAL);
  assert(bk7258_pcm_stop(session)==0); clean();
  statusbits=0;
  for(unsigned capture=0;capture<2;capture++)
    {
      assert(bk7258_pcm_start(capture,&session)==0);
      stuckirq=1; nxsig_usleep(10000); stuckirq=0;
      assert(bk7258_pcm_status(session,&s)==0 && s.error==-EIO && !s.running);
      assert(!pa && !started && !rxen && !txen);
      assert(bk7258_pcm_stop(session)==0); clean();
    }
  puts("PCM: sustained 6s capture/playback, partial ring I/O, wrap, overrun,");
  puts("underrun silence, bounds/ramp, drain/timeout, stale sessions, ownership,");
  puts("setup/interruption/IRQ errors and stop/wipe passed (simulation only)");
}
'''

if __name__ == '__main__':
    chip = pathlib.Path(sys.argv[1])
    code = (stub + '\nstatic int nxmutex_lock(mutex_t *m)'
            '{return nxmutex_trylock(m);}\n'
            + stripped(chip / 'include/bk7258_aud.h')
            + stripped(chip / 'include/bk7258_pcm.h')
            + '\nstatic unsigned expected_rate=16000;\n'
            + drivers.replace('c->samplerate==16000', 'c->samplerate==expected_rate')
            + stripped(chip / 'bk7258_pcm.c') + test)
    with tempfile.TemporaryDirectory(prefix='bk7258-pcm-') as tmp:
        path = pathlib.Path(tmp)
        (path / 'test.c').write_text(code)
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-g', str(path / 'test.c'),
                        '-o', str(path / 'test')], check=True)
        subprocess.run([str(path / 'test')], check=True)
