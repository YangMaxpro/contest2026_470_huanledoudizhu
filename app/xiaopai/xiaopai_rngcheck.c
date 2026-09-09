/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "xiaopai_rngcheck.h"

int xiaopai_rngcheck(void)
{
  uint8_t samples[8][32];
  size_t done = 0;
  unsigned int i;
  unsigned int j;
  int ret = 0;
  int fd = open("/dev/random", O_RDONLY);

  if (fd < 0)
    {
      ret = -errno;
      printf("RNG check failed: open /dev/random error=%d\n", -ret);
      return ret;
    }
  while (done < sizeof(samples))
    {
      ssize_t n = read(fd, (uint8_t *)samples + done, sizeof(samples) - done);
      if (n < 0 && errno == EINTR)
        {
          continue;
        }
      if (n <= 0)
        {
          ret = n < 0 ? -errno : -EIO;
          break;
        }
      done += n;
    }
  close(fd);
  if (ret == 0)
    {
      for (i = 0; i < 8; i++)
        {
          for (j = 0; j < i; j++)
            {
              if (memcmp(samples[i], samples[j], 32) == 0)
                {
                  ret = -EIO;
                }
            }
        }
    }
  explicit_bzero(samples, sizeof(samples));
  if (ret < 0)
    {
      printf("RNG check failed: bytes=%zu error=%d\n", done, -ret);
      return ret;
    }
  printf("RNG check v19 passed: CP TRNG, 256 bytes, 8 distinct blocks\n");
  printf("Transport/stuck-output check only; not entropy certification or TLS\n");
  return 0;
}
