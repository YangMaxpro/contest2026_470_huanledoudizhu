/****************************************************************************
 * Contest 2026 team 470 board - boot initialization
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Board: Agora & Broadcom "Conversational AI Dev Kit R1" (Beken BK7258)
 ****************************************************************************/

#include <errno.h>

#include <nuttx/board.h>
#include <nuttx/config.h>

#ifdef CONFIG_ARCH_BOARD_BK7258_DEVKIT

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
  /* Reserved for board-only peripherals.  UART0 is configured earlier in
   * bk7258_start.c, before the serial driver starts. */
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
