#!/usr/bin/env python3
"""Local loopback only; no cloud calls or credentials."""
import pathlib
import subprocess
import sys
import tempfile

source = pathlib.Path(sys.argv[1]).resolve()
test = r'''
#include <assert.h>
#include "rtsa_net.c"
int main(void) {
  struct rtsa_addrinfo hint={.family=2,.socktype=2,.flags=12}, *info=NULL;
  assert(!rtsa_lwip_getaddrinfo("127.0.0.1","0",&hint,&info));
  assert(info && info->addrlen==16 && ((unsigned char *)info->addr)[1]==2);
  int receiver=rtsa_lwip_socket(2,2,0), sender=rtsa_lwip_socket(2,2,0);
  assert(receiver>=0 && sender>=0);
  assert(!rtsa_lwip_bind(receiver,info->addr,info->addrlen));
  unsigned char addr[18]; memset(addr,0x55,sizeof(addr)); uint32_t size=16;
  assert(!rtsa_lwip_getsockname(receiver,addr+1,&size));
  assert(size==16 && addr[0]==0x55 && addr[17]==0x55);
  assert(rtsa_lwip_sendto(sender,"test",4,0,addr+1,16)==4);
  uint32_t readbits[2]={0}; readbits[receiver/32]=UINT32_C(1)<<(receiver%32);
  int32_t timeout[4]={1,0,0,0};
  assert(rtsa_lwip_select(receiver+1,readbits,NULL,NULL,timeout)==1);
  assert(readbits[receiver/32] & (UINT32_C(1)<<(receiver%32)));
  int option=1; uint32_t olen=4;
  assert(!rtsa_lwip_setsockopt(receiver,0xfff,4,&option,4));
  option=0; assert(!rtsa_lwip_getsockopt(receiver,0xfff,4,&option,&olen) && option);
  assert(rtsa_lwip_select(65,NULL,NULL,NULL,timeout)==-1 && errno==EINVAL);
  assert(!rtsa_lwip_setsockopt(receiver,0xfff,0x1006,timeout,16));
  char buf[8]={0}; unsigned char peer[16]; size=16;
  assert(rtsa_lwip_recvfrom(receiver,buf,8,0,peer,&size)==4);
  assert(!memcmp(buf,"test",4) && peer[1]==2);
  assert(rtsa_lwip_recv(receiver,buf,8,8)==-1 && (errno==EAGAIN || errno==EWOULDBLOCK));
  assert(!rtsa_lwip_connect(sender,addr+1,16));
  assert(rtsa_lwip_send(sender,"ok",2,0)==2);
  assert(rtsa_lwip_recv(receiver,buf,8,0)==2);
  size=1; assert(!rtsa_lwip_getpeername(sender,peer,&size) && size==16);
  assert(rtsa_lwip_socket(10,2,0)==-1 && errno==EAFNOSUPPORT);
  assert(rtsa_lwip_bind(receiver,addr,1)==-1 && errno==EINVAL);
  assert(message_flags(0x4000)==-1 && errno==EOPNOTSUPP);
  rtsa_lwip_freeaddrinfo(info);
  hint.family=10; info=NULL;
  assert(rtsa_lwip_getaddrinfo("127.0.0.1","80",&hint,&info)==204 && !info);
  assert(!rtsa_lwip_close(sender)); assert(!rtsa_lwip_close(receiver));
}
'''
with tempfile.TemporaryDirectory() as tmp:
    src = pathlib.Path(tmp) / "test.c"
    exe = pathlib.Path(tmp) / "test"
    src.write_text(test)
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-I"+str(source.parent), str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=15)
print("PASS RTSA IPv4: numeric resolution, UDP loopback, flags, address conversion, bounds and cleanup")
