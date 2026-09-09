/* SPDX-License-Identifier: Apache-2.0 */
#include <nuttx/config.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <netdb.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
#include "mbedtls/ctr_drbg.h"
#include "mbedtls/entropy.h"
#include "mbedtls/net_sockets.h"
#include "mbedtls/ssl.h"
#include "mbedtls/x509_crt.h"
#include "netutils/webclient.h"
#include "xiaopai_tls.h"
#include "xiaopai_tls_ca.h"

#ifndef MBEDTLS_HAVE_TIME_DATE
#error HTTPS requires certificate validity date checking
#endif
#ifndef XIAOPAI_RANDOM_DEVICE
#define XIAOPAI_RANDOM_DEVICE "/dev/random"
#endif

struct xiaopai_tls
{
  mbedtls_ssl_context ssl;
  mbedtls_ssl_config config;
  mbedtls_ctr_drbg_context drbg;
  mbedtls_x509_crt ca;
  int fd;
  bool connecting;
  bool ready;
  unsigned int poll_flags;
  int64_t deadline;
  int error;
  uint32_t verify_flags;
};

static bool tls_expired(const struct xiaopai_tls *tls)
{
  struct timespec now;
  return clock_gettime(CLOCK_MONOTONIC, &now) < 0 ||
         (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000 >= tls->deadline;
}

static int tls_entropy(void *arg, unsigned char *out, size_t len)
{
  struct xiaopai_tls *tls = arg;
  size_t done = 0;
  int fd = open(XIAOPAI_RANDOM_DEVICE, O_RDONLY);
  if (fd < 0)
    goto failed;
  while (done < len && !tls_expired(tls))
    {
      ssize_t n = read(fd, out + done, len - done);
      if (n < 0 && errno == EINTR)
        continue;
      if (n <= 0)
        break;
      done += n;
    }
  close(fd);
  if (done == len)
    return 0;
failed:
  explicit_bzero(out, len);
  return MBEDTLS_ERR_ENTROPY_SOURCE_FAILED;
}

static int tls_send_raw(void *arg, const unsigned char *buf, size_t len)
{
  struct xiaopai_tls *tls = arg;
  ssize_t n = send(tls->fd, buf, len, 0);
  if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR))
    return MBEDTLS_ERR_SSL_WANT_WRITE;
  return n < 0 ? MBEDTLS_ERR_NET_SEND_FAILED : (int)n;
}

static int tls_recv_raw(void *arg, unsigned char *buf, size_t len)
{
  struct xiaopai_tls *tls = arg;
  ssize_t n = recv(tls->fd, buf, len, 0);
  if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR))
    return MBEDTLS_ERR_SSL_WANT_READ;
  return n < 0 ? MBEDTLS_ERR_NET_RECV_FAILED : (int)n;
}

static int tls_result(struct xiaopai_tls *tls, int ret)
{
  tls->poll_flags = 0;
  if (ret == MBEDTLS_ERR_SSL_WANT_READ || ret == MBEDTLS_ERR_SSL_WANT_WRITE)
    {
      tls->poll_flags = ret == MBEDTLS_ERR_SSL_WANT_READ ?
                       WEBCLIENT_POLL_INFO_WANT_READ : WEBCLIENT_POLL_INFO_WANT_WRITE;
      return -EAGAIN;
    }
  if (ret < 0)
    {
      tls->error = ret;
      tls->verify_flags = mbedtls_ssl_get_verify_result(&tls->ssl);
      return -EIO;
    }
  return ret;
}

static int tls_connect(void *arg, const char *hostname, const char *port,
                       unsigned int timeout, struct webclient_tls_connection **conn)
{
  struct xiaopai_tls *tls = arg;
  int ret;
  (void)timeout;
  *conn = (struct webclient_tls_connection *)tls;
  if (tls_expired(tls))
    return -ETIMEDOUT;
  if (tls->ready)
    return 0;
  if (tls->fd < 0)
    {
      struct addrinfo hints = {0};
      struct addrinfo *addresses = NULL;
      struct addrinfo *address;
      hints.ai_family = AF_INET;
      hints.ai_socktype = SOCK_STREAM;
      if (getaddrinfo(hostname, port, &hints, &addresses) != 0)
        return -EHOSTUNREACH;
      if (tls_expired(tls))
        {
          freeaddrinfo(addresses);
          return -ETIMEDOUT;
        }
      ret = -EHOSTUNREACH;
      for (address = addresses; address != NULL; address = address->ai_next)
        {
          int flags;
          tls->fd = socket(address->ai_family, address->ai_socktype, address->ai_protocol);
          if (tls->fd < 0)
            continue;
          flags = fcntl(tls->fd, F_GETFL, 0);
          if (flags < 0 || fcntl(tls->fd, F_SETFL, flags | O_NONBLOCK) < 0)
            {
              ret = -errno;
              close(tls->fd);
              tls->fd = -1;
              continue;
            }
          ret = connect(tls->fd, address->ai_addr, address->ai_addrlen);
          if (ret == 0 || errno == EINPROGRESS || errno == EINTR)
            {
              tls->connecting = ret != 0;
              ret = 0;
              break;
            }
          ret = -errno;
          close(tls->fd);
          tls->fd = -1;
        }
      freeaddrinfo(addresses);
      if (ret < 0)
        return ret;
      ret = mbedtls_ssl_set_hostname(&tls->ssl, hostname);
      if (ret != 0)
        return tls_result(tls, ret);
      mbedtls_ssl_set_bio(&tls->ssl, tls, tls_send_raw, tls_recv_raw, NULL);
      if (tls->connecting)
        {
          tls->poll_flags = WEBCLIENT_POLL_INFO_WANT_WRITE;
          return -EAGAIN;
        }
    }
  else if (tls->connecting)
    {
      int error = 0;
      socklen_t len = sizeof(error);
      if (getsockopt(tls->fd, SOL_SOCKET, SO_ERROR, &error, &len) < 0)
        return -errno;
      if (error != 0)
        return -error;
      tls->connecting = false;
    }
  ret = tls_result(tls, mbedtls_ssl_handshake(&tls->ssl));
  if (ret == 0)
    {
      tls->verify_flags = mbedtls_ssl_get_verify_result(&tls->ssl);
      if (tls->verify_flags != 0)
        return -EACCES;
      tls->ready = true;
      printf("TLS verified: %s, %s\n", mbedtls_ssl_get_version(&tls->ssl),
             mbedtls_ssl_get_ciphersuite(&tls->ssl));
    }
  return ret;
}

static ssize_t tls_send(void *arg, struct webclient_tls_connection *conn,
                        const void *buf, size_t len)
{
  struct xiaopai_tls *tls = arg;
  (void)conn;
  if (tls_expired(tls))
    return -ETIMEDOUT;
  if (!tls->ready)
    return -ENOTCONN;
  return tls_result(tls, mbedtls_ssl_write(&tls->ssl, buf, len));
}

static ssize_t tls_recv(void *arg, struct webclient_tls_connection *conn,
                        void *buf, size_t len)
{
  struct xiaopai_tls *tls = arg;
  int ret;
  (void)conn;
  if (tls_expired(tls))
    return -ETIMEDOUT;
  if (!tls->ready)
    return -ENOTCONN;
  ret = mbedtls_ssl_read(&tls->ssl, buf, len);
  if (ret == MBEDTLS_ERR_SSL_PEER_CLOSE_NOTIFY)
    return 0;
  /* Bare TCP EOF is not an authenticated TLS close. */
  if (ret == 0)
    return -ECONNRESET;
  return tls_result(tls, ret);
}

static int tls_close(void *arg, struct webclient_tls_connection *conn)
{
  struct xiaopai_tls *tls = arg;
  (void)conn;
  if (tls->fd >= 0)
    {
      if (tls->ready)
        (void)mbedtls_ssl_close_notify(&tls->ssl); /* Best effort, nonblocking. */
      close(tls->fd);
      tls->fd = -1;
    }
  return 0;
}

static int tls_poll(void *arg, struct webclient_tls_connection *conn,
                    struct webclient_poll_info *info)
{
  struct xiaopai_tls *tls = arg;
  (void)conn;
  info->fd = tls->fd;
  info->flags = tls->poll_flags;
  return tls->fd < 0 || tls->poll_flags == 0 ? -EIO : 0;
}

const struct webclient_tls_ops g_xiaopai_tls_ops =
{
  .connect = tls_connect,
  .send = tls_send,
  .recv = tls_recv,
  .close = tls_close,
  .get_poll_info = tls_poll,
};

int xiaopai_tls_create(struct xiaopai_tls **out, int64_t deadline)
{
  static const unsigned char personalization[] = "xiaopai-https-v21";
  struct xiaopai_tls *tls;
  int ret;
  *out = NULL;
  /* Sanity gate only: the operator must set accurate UTC before TLS. */
  if (time(NULL) < (time_t)1735689600)
    {
      printf("HTTPS blocked: set accurate UTC with date -u -s first\n");
      return -EINVAL;
    }
  tls = calloc(1, sizeof(*tls));
  if (tls == NULL)
    return -ENOMEM;
  tls->fd = -1;
  tls->deadline = deadline;
  mbedtls_ssl_init(&tls->ssl);
  mbedtls_ssl_config_init(&tls->config);
  mbedtls_ctr_drbg_init(&tls->drbg);
  mbedtls_x509_crt_init(&tls->ca);
  ret = mbedtls_x509_crt_parse(&tls->ca, (const unsigned char *)g_xiaopai_tls_ca,
                              sizeof(g_xiaopai_tls_ca));
  if (ret == 0)
    ret = mbedtls_ctr_drbg_seed(&tls->drbg, tls_entropy, tls,
                                personalization, sizeof(personalization) - 1);
  if (ret == 0)
    ret = mbedtls_ssl_config_defaults(&tls->config, MBEDTLS_SSL_IS_CLIENT,
                                      MBEDTLS_SSL_TRANSPORT_STREAM,
                                      MBEDTLS_SSL_PRESET_DEFAULT);
  if (ret == 0)
    {
      mbedtls_ssl_conf_authmode(&tls->config, MBEDTLS_SSL_VERIFY_REQUIRED);
      mbedtls_ssl_conf_ca_chain(&tls->config, &tls->ca, NULL);
      mbedtls_ssl_conf_rng(&tls->config, mbedtls_ctr_drbg_random, &tls->drbg);
      mbedtls_ssl_conf_min_version(&tls->config, MBEDTLS_SSL_MAJOR_VERSION_3,
                                   MBEDTLS_SSL_MINOR_VERSION_3);
      mbedtls_ssl_conf_max_version(&tls->config, MBEDTLS_SSL_MAJOR_VERSION_3,
                                   MBEDTLS_SSL_MINOR_VERSION_3);
      ret = mbedtls_ssl_setup(&tls->ssl, &tls->config);
    }
  if (ret != 0)
    {
      printf("TLS initialization failed: -0x%04x\n", (unsigned int)-ret);
      xiaopai_tls_destroy(tls);
      return -EIO;
    }
  *out = tls;
  return 0;
}

void xiaopai_tls_report(const struct xiaopai_tls *tls)
{
  if (tls != NULL && (tls->error != 0 || tls->verify_flags != 0))
    printf("TLS detail: error=-0x%04x verify_flags=0x%08" PRIx32 "\n",
           (unsigned int)-tls->error, tls->verify_flags);
}

void xiaopai_tls_destroy(struct xiaopai_tls *tls)
{
  if (tls == NULL)
    return;
  tls_close(tls, NULL);
  mbedtls_ssl_free(&tls->ssl);
  mbedtls_ssl_config_free(&tls->config);
  mbedtls_x509_crt_free(&tls->ca);
  mbedtls_ctr_drbg_free(&tls->drbg);
  explicit_bzero(tls, sizeof(*tls));
  free(tls);
}
