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
 *   Early board initialization, called from nx_start() before the serial
 *   console is fully up.  For the BK7258 DevKit this is the place to:
 *
 *     - enable the UART0 clock gate (system control unit registers)
 *     - route the UART0 TX/RX pins through the GPIO matrix
 *       (see Beken Armino SDK: gpio_map.h, UART0_TX_PIN / UART0_RX_PIN)
 *     - bring up the 26 MHz crystal / PLL if not started by the bootloader
 *
 *   NOTE: first bring-up step is compile validation (L0); the pin mux and
 *   clock gate register details are documented in the Armino SDK and will
 *   be wired up on real hardware bring-up.
 *
 ****************************************************************************/

void openvela_board_initialize(void)
{
  /* TODO(BK7258): enable UART0 clock gate + GPIO mux for real hardware.
   *   - SYSTEM_CTRL_UART0_CLK_GATE via the system control unit
   *   - UART0_TX_PIN (GPIO 1) / UART0_RX_PIN (GPIO 2) muxed as UART function
   */
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
