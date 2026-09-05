/****************************************************************************
 * boards/arm/bk7258/bk7258-devkit/include/board.h
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.  The
 * ASF licenses this file to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance with the
 * License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
 * License for the specific language governing permissions and limitations
 * under the License.
 *
 ****************************************************************************/

#ifndef __BOARDS_ARM_BK7258_BK7258_DEVKIT_INCLUDE_BOARD_H
#define __BOARDS_ARM_BK7258_BK7258_DEVKIT_INCLUDE_BOARD_H

/****************************************************************************
 * Included Files
 ****************************************************************************/

#include <nuttx/config.h>

#include <stdbool.h>
#include <stdint.h>

/****************************************************************************
 * Pre-processor Definitions
 ****************************************************************************/

/* Crystal frequency of the BK7258 SoC.  UART baud rate is derived from
 * this clock: baud = XTAL_FREQ / (clk_div + 1).
 */

#define BK7258_BOARD_XTAL_FREQ      26000000

/* Board UART muxing (used by the real-hardware bring-up, the board
 * schematic routes UART0 to these GPIOs):
 *
 *   UART0_TX: GPIO11
 *   UART0_RX: GPIO10
 */

#define BK7258_BOARD_UART0_TX_PIN   11
#define BK7258_BOARD_UART0_RX_PIN   10
#define BK7258_BOARD_UART0_BAUD      115200

/* R1 status LEDs.  The Agora reference application registers these pins as
 * red=GPIO40 and green=GPIO41, and drives a high output to turn an LED on. */

#define BK7258_BOARD_RED_LED_PIN     40
#define BK7258_BOARD_GREEN_LED_PIN   41
#define BK7258_BOARD_LED_ACTIVE_HIGH 1

/* BK7258 AON GPIO and system function registers (SPE address map). */

#define BK7258_BOARD_SYS_REG_BASE    0x44010000u
#define BK7258_BOARD_AON_GPIO_BASE   0x44000400u
#define BK7258_BOARD_GPIO_FUNC_BASE  (BK7258_BOARD_SYS_REG_BASE + 0xc0u)

#define BK7258_BOARD_GPIO_VALUE      (1u << 1)
#define BK7258_BOARD_GPIO_MODE_MASK  (3u << 2)
#define BK7258_BOARD_GPIO_PULL_MODE  (1u << 4)
#define BK7258_BOARD_GPIO_PULL_EN    (1u << 5)
#define BK7258_BOARD_GPIO_2ND_FUNC   (1u << 6)

enum bk7258_board_feedback_e
{
  BK7258_BOARD_FEEDBACK_OFF = 0,
  BK7258_BOARD_FEEDBACK_LISTENING,
  BK7258_BOARD_FEEDBACK_THINKING,
  BK7258_BOARD_FEEDBACK_RESPONDING,
  BK7258_BOARD_FEEDBACK_REMINDER,
  BK7258_BOARD_FEEDBACK_ERROR
};

/****************************************************************************
 * Public Data
 ****************************************************************************/

#ifndef __ASSEMBLY__

#undef EXTERN
#if defined(__cplusplus)
#define EXTERN extern "C"
extern "C"
{
#else
#define EXTERN extern
#endif

/****************************************************************************
 * Public Function Prototypes
 ****************************************************************************/

EXTERN int bk7258_board_set_feedback(enum bk7258_board_feedback_e feedback);
EXTERN int bk7258_board_set_led(unsigned int led, bool on);
EXTERN bool bk7258_board_feedback_available(void);

#undef EXTERN
#if defined(__cplusplus)
}
#endif

#endif /* __ASSEMBLY__ */
#endif /* __BOARDS_ARM_BK7258_BK7258_DEVKIT_INCLUDE_BOARD_H */
