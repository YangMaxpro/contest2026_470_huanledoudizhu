/****************************************************************************
 * Contest 2026 team 470 board - boot initialization
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Board: Agora & Broadcom "Conversational AI Dev Kit R1" (Beken BK7258)
 ****************************************************************************/

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include <nuttx/board.h>
#include <nuttx/config.h>
#include <nuttx/irq.h>
#include <nuttx/spinlock.h>
#ifdef CONFIG_FS_PROCFS
#  include <nuttx/fs/fs.h>
#endif

#include "../include/board.h"
#include "hardware/bk7258_mbox.h"

#ifdef CONFIG_BK7258_WIFI
#  include "bk7258_wifi.h"
#endif

#ifdef CONFIG_ARCH_BOARD_BK7258_DEVKIT

static inline uint32_t bk7258_board_read(uintptr_t address)
{
  return *(volatile uint32_t *)address;
}

static inline void bk7258_board_write(uintptr_t address, uint32_t value)
{
  *(volatile uint32_t *)address = value;
}

static int bk7258_board_configure_led(unsigned int pin, bool on)
{
  uintptr_t func_address;
  uintptr_t gpio_address;
  uint32_t func_shift;
  uint32_t value;

  if (pin >= 56)
    {
      return -EINVAL;
    }

  /* Each system-function register contains eight four-bit pin selectors.
   * Selector zero is the ordinary GPIO function. */

  func_address = BK7258_BOARD_GPIO_FUNC_BASE + (pin / 8) * 4;
  func_shift = (pin % 8) * 4;
  value = bk7258_board_read(func_address);
  value &= ~(0xfu << func_shift);
  bk7258_board_write(func_address, value);

  /* Keep unrelated GPIO fields intact.  In particular, do not write the
   * whole word with 0x2/0x0: the SDK uses bit 3 as an active-low output
   * enable, and other bits may belong to pull or alternate-function setup. */

  gpio_address = BK7258_BOARD_AON_GPIO_BASE + pin * 4;
  value = bk7258_board_read(gpio_address);
  value &= ~(BK7258_BOARD_GPIO_MODE_MASK |
             BK7258_BOARD_GPIO_VALUE |
             BK7258_BOARD_GPIO_PULL_MODE |
             BK7258_BOARD_GPIO_PULL_EN |
             BK7258_BOARD_GPIO_2ND_FUNC);
  if (on == (BK7258_BOARD_LED_ACTIVE_HIGH != 0))
    {
      value |= BK7258_BOARD_GPIO_VALUE;
    }

  bk7258_board_write(gpio_address, value);
  return 0;
}

bool bk7258_board_feedback_available(void)
{
  return true;
}

void bk7258_board_audio_pa(bool enabled)
{
  /* GPIO50 -> R70 -> PA CTRL; R71 pulls down to shutdown. */
  irqstate_t flags = enter_critical_section();
  uintptr_t gpio = BK7258_BOARD_AON_GPIO_BASE + 50 * 4;
  uintptr_t func = BK7258_BOARD_GPIO_FUNC_BASE + (50 / 8) * 4;
  uint32_t value = bk7258_board_read(gpio);

  value &= ~(BK7258_BOARD_GPIO_MODE_MASK | BK7258_BOARD_GPIO_VALUE |
             BK7258_BOARD_GPIO_PULL_MODE | BK7258_BOARD_GPIO_PULL_EN |
             BK7258_BOARD_GPIO_2ND_FUNC);
  if (enabled)
    {
      value |= BK7258_BOARD_GPIO_VALUE;
    }

  bk7258_board_write(gpio, value);
  value = bk7258_board_read(func) & ~(0xfu << ((50 % 8) * 4));
  bk7258_board_write(func, value);
  leave_critical_section(flags);
}

int bk7258_board_set_led(unsigned int led, bool on)
{
  unsigned int pin;

  if (led == 0)
    {
      pin = BK7258_BOARD_RED_LED_PIN;
    }
  else if (led == 1)
    {
      pin = BK7258_BOARD_GREEN_LED_PIN;
    }
  else
    {
      return -EINVAL;
    }

  return bk7258_board_configure_led(pin, on);
}

int bk7258_board_set_feedback(enum bk7258_board_feedback_e feedback)
{
  bool red;
  bool green;

  switch (feedback)
    {
      case BK7258_BOARD_FEEDBACK_LISTENING:
        red = false;
        green = true;
        break;

      case BK7258_BOARD_FEEDBACK_THINKING:
        red = true;
        green = true;
        break;

      case BK7258_BOARD_FEEDBACK_RESPONDING:
        red = false;
        green = true;
        break;

      case BK7258_BOARD_FEEDBACK_REMINDER:
      case BK7258_BOARD_FEEDBACK_ERROR:
        red = true;
        green = false;
        break;

      case BK7258_BOARD_FEEDBACK_OFF:
        red = false;
        green = false;
        break;

      default:
        return -EINVAL;
    }

  if (bk7258_board_set_led(0, red) < 0 ||
      bk7258_board_set_led(1, green) < 0)
    {
      return -EIO;
    }

  return 0;
}

/****************************************************************************
 * Public Functions
 ****************************************************************************/

/****************************************************************************
 * Name: openvela_board_initialize
 *
 * Description:
 *   The chip reset entry configures the UART0 clock and GPIO matrix before
 *   early serial initialization.  This board hook is intentionally kept free
 *   of console register writes so GPIO11 TX / GPIO10 RX are not reprogrammed
 *   after the chip-level setup.
 *
 ****************************************************************************/

void openvela_board_initialize(void)
{
#ifdef CONFIG_BK7258_AUDIO
  bk7258_board_audio_pa(false);
#endif
  /* UART0 is configured earlier in bk7258_start.c.  Leave both status LEDs
   * off until an application state claims them. */
  (void)bk7258_board_set_feedback(BK7258_BOARD_FEEDBACK_OFF);
}

/****************************************************************************
 * Name: board_early_initialize
 *
 * Description:
 *   Called from nx_start() on the startup thread when
 *   CONFIG_BOARD_EARLY_INITIALIZE is enabled.
 *
 ****************************************************************************/

void board_early_initialize(void)
{
  openvela_board_initialize();
}

#ifdef CONFIG_BOARD_LATE_INITIALIZE

void board_late_initialize(void)
{
  int ret;

  /* The CP's CPU1 boot watchdog waits for the AP's PWC boot-ready frame.
   * Start that service before waiting for the ordinary UART/mailbox probe;
   * the transport explicitly permits this one bootstrap frame during probe.
   */
  ret = bk7258_pwc_start();
  if (ret < 0)
    {
      printf("BK7258 PWC boot-ready failed: %d\n", ret);
      return;
    }

  /* Start HW_CTRL IPC before waiting for the UART link. The CP only marks
   * the AP console ready after it receives this power-up indication; waiting
   * for the link first would deadlock with ready_flags stuck at 0x5. */
  ret = bk7258_ipc_heartbeat_start();
  if (ret < 0)
    {
      printf("BK7258 IPC heartbeat failed: %d\n", ret);
      return;
    }

  ret = bk7258_mailbox_wait_link_ready(8000);
  if (ret < 0)
    {
      printf("BK7258 mailbox link failed: %d\n", ret);
      bk7258_mailbox_dump_stats();
      return;
    }

  printf("BK7258 mailbox, heartbeat and CPU1 boot-ready services active\n");

#ifdef CONFIG_BK7258_PSRAM
  ret = bk7258_pwc_psram_start();
  if (ret < 0)
    {
      /* Voice will reject allocation; retain the console and networking. */
      printf("BK7258 PSRAM unavailable: %d; voice disabled, boot continues\n", ret);
    }
#endif

#ifdef CONFIG_FS_PROCFS
  ret = nx_mount(NULL, "/proc", "procfs", 0, NULL);
  if (ret < 0 && ret != -EBUSY)
    {
      printf("BK7258 procfs mount failed: %d\n", ret);
    }
#endif

#ifdef CONFIG_BK7258_WIFI
  ret = bk7258_wifi_initialize();
  if (ret < 0)
    {
      printf("BK7258 Wi-Fi initialization failed: %d\n", ret);
      return;
    }

  printf("BK7258 Wi-Fi netdev initialized\n");
#endif
}

#endif /* CONFIG_BOARD_LATE_INITIALIZE */

#ifdef CONFIG_BOARDCTL

/****************************************************************************
 * Name: board_app_initialize
 *
 * Description:
 *   Perform application specific initialization.  This function is never
 *   called directly from application code, but only indirectly via the
 *   (non-standard) boardctl() interface using the command BOARDIOC_INIT.
 *
 ****************************************************************************/

int board_app_initialize(uintptr_t arg)
{
  UNUSED(arg);
  return 0;
}

#endif /* CONFIG_BOARDCTL */

#endif /* CONFIG_ARCH_BOARD_BK7258_DEVKIT */
