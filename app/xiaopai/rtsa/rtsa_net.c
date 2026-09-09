/* SPDX-License-Identifier: Apache-2.0 */
/* Explicit IPv4 lwIP ABI translation for the experimental probe. */
#include <arpa/inet.h>
#include <errno.h>
#include <netdb.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <sys/ioctl.h>
#include <sys/time.h>
#include <netinet/tcp.h>
#include <unistd.h>
#include "rtsa_trace.h"

struct rtsa_addrinfo
{
  int flags, family, socktype, protocol;
  uint32_t addrlen;
  void *addr;
  char *canonname;
  struct rtsa_addrinfo *next;
};

static int net_error(int error)
{
  errno = error;
  return -1;
}

static int address_in(const void *vendor, uint32_t length, struct sockaddr_in *native)
{
  const unsigned char *p = vendor;
  if (!p || length < 16) return net_error(EINVAL);
  if (p[1] != 2) return net_error(EAFNOSUPPORT);
  memset(native, 0, sizeof(*native));
  native->sin_family = AF_INET;
  memcpy(&native->sin_port, p + 2, 2);
  memcpy(&native->sin_addr, p + 4, 4);
  return 0;
}

static int address_out(const struct sockaddr_in *native, void *vendor, uint32_t *length)
{
  unsigned char bytes[16] = {16, 2};
  if (!vendor || !length) return net_error(EINVAL);
  if (native->sin_family != AF_INET) return net_error(EAFNOSUPPORT);
  memcpy(bytes + 2, &native->sin_port, 2);
  memcpy(bytes + 4, &native->sin_addr, 4);
  memcpy(vendor, bytes, *length < sizeof(bytes) ? *length : sizeof(bytes));
  *length = sizeof(bytes);
  return 0;
}

static int message_flags(int flags)
{
  int result = 0;
  if (flags & ~0x2b) return net_error(EOPNOTSUPP);
  if (flags & 1) result |= MSG_PEEK;
  if (flags & 2) result |= MSG_WAITALL;
  if (flags & 8) result |= MSG_DONTWAIT;
  if (flags & 32) result |= MSG_NOSIGNAL;
  return result;
}

int rtsa_lwip_socket(int domain, int type, int protocol)
{
  if (domain != 2) return net_error(EAFNOSUPPORT);
  if (type != 1 && type != 2) return net_error(EPROTONOSUPPORT);
  if (protocol != 0 && protocol != 6 && protocol != 17)
    return net_error(EPROTONOSUPPORT);
  int fd = socket(AF_INET, type == 1 ? SOCK_STREAM : SOCK_DGRAM, protocol);
  if (fd >= 64) { close(fd); return net_error(EMFILE); }
  return fd;
}

int rtsa_lwip_bind(int fd, const void *address, uint32_t length)
{
  struct sockaddr_in native;
  if (address_in(address, length, &native)) return -1;
  return bind(fd, (struct sockaddr *)&native, sizeof(native));
}

int rtsa_lwip_connect(int fd, const void *address, uint32_t length)
{
  struct sockaddr_in native;
  if (address_in(address, length, &native)) return -1;
  return connect(fd, (struct sockaddr *)&native, sizeof(native));
}

int rtsa_lwip_getsockname(int fd, void *address, uint32_t *length)
{
  struct sockaddr_in native;
  socklen_t n = sizeof(native);
  if (!address || !length) return net_error(EINVAL);
  if (getsockname(fd, (struct sockaddr *)&native, &n)) return -1;
  return address_out(&native, address, length);
}

int rtsa_lwip_getpeername(int fd, void *address, uint32_t *length)
{
  struct sockaddr_in native;
  socklen_t n = sizeof(native);
  if (!address || !length) return net_error(EINVAL);
  if (getpeername(fd, (struct sockaddr *)&native, &n)) return -1;
  return address_out(&native, address, length);
}

int rtsa_lwip_accept(int fd, void *address, uint32_t *length)
{
  struct sockaddr_in native;
  socklen_t n = sizeof(native);
  if (address && !length) return net_error(EINVAL);
  int accepted = accept(fd, address ? (struct sockaddr *)&native : NULL,
                        address ? &n : NULL);
  if (accepted >= 64) { close(accepted); return net_error(EMFILE); }
  if (accepted >= 0 && address && address_out(&native, address, length))
    { int error = errno; close(accepted); return net_error(error); }
  return accepted;
}

int rtsa_lwip_listen(int fd, int backlog) { return listen(fd, backlog); }
int rtsa_lwip_close(int fd)
{
  RTSA_TRACE("close begin", fd, 0);
  int ret = close(fd);
  int error = errno;
  RTSA_TRACE("close end", fd, ret < 0 ? -error : ret);
  errno = error;
  return ret;
}
ssize_t rtsa_lwip_read(int fd, void *p, size_t n) { return read(fd, p, n); }
ssize_t rtsa_lwip_write(int fd, const void *p, size_t n) { return write(fd, p, n); }

ssize_t rtsa_lwip_send(int fd, const void *data, size_t n, int flags)
{
  int native = message_flags(flags);
  return native < 0 ? -1 : send(fd, data, n, native);
}

ssize_t rtsa_lwip_recv(int fd, void *data, size_t n, int flags)
{
  int native = message_flags(flags);
  return native < 0 ? -1 : recv(fd, data, n, native);
}

ssize_t rtsa_lwip_sendto(int fd, const void *data, size_t n, int flags,
                        const void *address, uint32_t length)
{
  struct sockaddr_in native;
  int converted = message_flags(flags);
  if (converted < 0 || address_in(address, length, &native)) return -1;
  return sendto(fd, data, n, converted, (struct sockaddr *)&native, sizeof(native));
}

ssize_t rtsa_lwip_recvfrom(int fd, void *data, size_t n, int flags,
                          void *address, uint32_t *length)
{
  struct sockaddr_in native;
  socklen_t size = sizeof(native);
  int converted = message_flags(flags);
  if (converted < 0) return -1;
  if (address && !length) return net_error(EINVAL);
  ssize_t result = recvfrom(fd, data, n, converted,
                            address ? (struct sockaddr *)&native : NULL,
                            address ? &size : NULL);
  if (result >= 0 && address && address_out(&native, address, length)) return -1;
  return result;
}

void rtsa_lwip_freeaddrinfo(struct rtsa_addrinfo *info)
{
  while (info)
    {
      struct rtsa_addrinfo *next = info->next;
      free(info->canonname);
      free(info->addr);
      free(info);
      info = next;
    }
}

int rtsa_lwip_getaddrinfo(const char *host, const char *service,
                         const struct rtsa_addrinfo *hints, struct rtsa_addrinfo **out)
{
  struct addrinfo native = {0}, *resolved = NULL;
  struct rtsa_addrinfo **tail;
  if (!out) return 202;
  *out = NULL;
  tail = out;
  native.ai_family = AF_INET;
  if (hints)
    {
      if (hints->family != 0 && hints->family != 2) return 204;
      if (hints->flags & ~15) return 202;
      if (hints->flags & 1) native.ai_flags |= AI_PASSIVE;
      if (hints->flags & 2) native.ai_flags |= AI_CANONNAME;
      if (hints->flags & 4) native.ai_flags |= AI_NUMERICHOST;
      if (hints->flags & 8) native.ai_flags |= AI_NUMERICSERV;
      if (hints->socktype != 0 && hints->socktype != 1 && hints->socktype != 2) return 201;
      native.ai_socktype = hints->socktype == 1 ? SOCK_STREAM : hints->socktype == 2 ? SOCK_DGRAM : 0;
      native.ai_protocol = hints->protocol;
    }
  int error = getaddrinfo(host, service, &native, &resolved);
  if (error) return error == EAI_MEMORY ? 203 : error == EAI_NONAME ? 200 : 202;
  for (struct addrinfo *p = resolved; p; p = p->ai_next)
    {
      if (p->ai_family != AF_INET || p->ai_addrlen < sizeof(struct sockaddr_in)) continue;
      struct rtsa_addrinfo *v = calloc(1, sizeof(*v));
      if (!v) { error = 203; break; }
      *tail = v;
      tail = &v->next;
      v->addr = malloc(16);
      v->addrlen = 16;
      if (!v->addr) { error = 203; break; }
      address_out((struct sockaddr_in *)p->ai_addr, v->addr, &v->addrlen);
      v->family = 2;
      v->socktype = p->ai_socktype == SOCK_STREAM ? 1 : 2;
      v->protocol = p->ai_protocol;
      if (p->ai_canonname)
        {
          v->canonname = strdup(p->ai_canonname);
          if (!v->canonname) { error = 203; break; }
        }
    }
  freeaddrinfo(resolved);
  if (!error && !*out) error = 200;
  if (error) { rtsa_lwip_freeaddrinfo(*out); *out = NULL; }
  return error;
}

/* Vendor sysroot fd_set has two 32-bit words, indexed by descriptor.
 * It is not the fallback lwIP byte array with LWIP_SOCKET_OFFSET. */
int rtsa_lwip_select(int count, void *readset, void *writeset, void *exceptset,
                     const void *timeout)
{
  fd_set native[3];
  void *vendor[3] = {readset, writeset, exceptset};
  uint32_t bits[3][2] = {{0}};
  struct timeval tv;
  if (count < 0 || count > 64 || count > FD_SETSIZE) return net_error(EINVAL);
  for (int i = 0; i < 3; i++)
    {
      FD_ZERO(&native[i]);
      if (vendor[i]) memcpy(bits[i], vendor[i], sizeof(bits[i]));
      for (int fd = 0; fd < count; fd++)
        if (bits[i][fd / 32] & (UINT32_C(1) << (fd % 32))) FD_SET(fd, &native[i]);
    }
  if (timeout)
    {
      int64_t seconds;
      int32_t micros;
      memcpy(&seconds, timeout, 8);
      memcpy(&micros, (const char *)timeout + 8, 4);
      if (seconds < 0 || micros < 0 || micros >= 1000000) return net_error(EINVAL);
      tv.tv_sec = seconds; tv.tv_usec = micros;
      if ((int64_t)tv.tv_sec != seconds) return net_error(EOVERFLOW);
    }
  int ret = select(count, readset ? &native[0] : NULL, writeset ? &native[1] : NULL,
                   exceptset ? &native[2] : NULL, timeout ? &tv : NULL);
  if (ret >= 0)
    for (int i = 0; i < 3; i++)
      if (vendor[i])
        {
          memset(bits[i], 0, sizeof(bits[i]));
          for (int fd = 0; fd < count; fd++)
            if (FD_ISSET(fd, &native[i])) bits[i][fd / 32] |= UINT32_C(1) << (fd % 32);
          memcpy(vendor[i], bits[i], sizeof(bits[i]));
        }
  return ret;
}

int rtsa_lwip_ioctl(int fd, unsigned long command, void *value)
{
  if (!value) return net_error(EINVAL);
  if (command == 0x8004667eUL) return ioctl(fd, FIONBIO, value);
  if (command == 0x4004667fUL) return ioctl(fd, FIONREAD, value);
  return net_error(ENOTTY);
}

static int socket_option(int *level, int option)
{
  if (*level == 6 && option == 1) { *level = IPPROTO_TCP; return TCP_NODELAY; }
  if (*level != 0xfff) return net_error(ENOPROTOOPT);
  *level = SOL_SOCKET;
  switch (option)
    {
      case 4: return SO_REUSEADDR;
      case 8: return SO_KEEPALIVE;
      case 32: return SO_BROADCAST;
      case 0x1001: return SO_SNDBUF;
      case 0x1002: return SO_RCVBUF;
      case 0x1005: return SO_SNDTIMEO;
      case 0x1006: return SO_RCVTIMEO;
      case 0x1007: return SO_ERROR;
      case 0x1008: return SO_TYPE;
      default: return net_error(ENOPROTOOPT);
    }
}

int rtsa_lwip_setsockopt(int fd, int level, int option, const void *value, uint32_t length)
{
  int timeout = level == 0xfff && (option == 0x1005 || option == 0x1006);
  int native = socket_option(&level, option);
  if (native < 0) return -1;
  if (!value) return net_error(EINVAL);
  if (timeout)
    {
      int64_t seconds;
      int32_t micros;
      if (length != 16) return net_error(EINVAL);
      memcpy(&seconds, value, 8);
      memcpy(&micros, (const char *)value + 8, 4);
      if (seconds < 0 || micros < 0 || micros >= 1000000) return net_error(EINVAL);
      struct timeval tv = {.tv_sec=seconds, .tv_usec=micros};
      if ((int64_t)tv.tv_sec != seconds) return net_error(EOVERFLOW);
      return setsockopt(fd, level, native, &tv, sizeof(tv));
    }
  if (length != sizeof(int)) return net_error(EINVAL);
  return setsockopt(fd, level, native, value, length);
}

int rtsa_lwip_getsockopt(int fd, int level, int option, void *value, uint32_t *length)
{
  if (!value || !length || *length < sizeof(int)) return net_error(EINVAL);
  if (level == 0xfff && (option == 0x1005 || option == 0x1006))
    return net_error(ENOPROTOOPT);
  int native = socket_option(&level, option);
  if (native < 0) return -1;
  int result;
  socklen_t n = sizeof(result);
  if (getsockopt(fd, level, native, &result, &n)) return -1;
  if (option == 0x1008) result = result == SOCK_STREAM ? 1 : result == SOCK_DGRAM ? 2 : 3;
  memcpy(value, &result, sizeof(result)); *length = sizeof(result);
  return 0;
}
