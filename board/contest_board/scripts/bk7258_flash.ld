/****************************************************************************
 * boards/contest2026_470_board/scripts/bk7258_flash.ld
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

/* BK7258 memory layout (Beken Armino SDK, SPE mode):
 *
 *   flash (rx)  : 8MB NOR flash, AP app in NOR at physical 0x165000,
 *                 XIP alias 0x02150000 (physical / 34 * 32)
 *   sram  (rwx) : AP core SRAM, 336K at 0x28010000 (0x28000000-0x2800ffff
 *                 is reserved for the AP spinlock region; see ram_regions.csv:
 *                 AP_RAM, 0x054000 bytes)
 *
 * Code runs XIP from the flash alias, .data/.bss live in SRAM.  An
 * additional 8M PSRAM heap region is added at runtime by
 * bk7258_allocateheap.c (CONFIG_MM_REGIONS > 1).
 */

MEMORY
{
  flash (rx)  : ORIGIN = 0x02150000, LENGTH = 8M - 0x150000
  sram  (rwx) : ORIGIN = 0x28010000, LENGTH = 336K
}

OUTPUT_ARCH(arm)
EXTERN(_vectors)
ENTRY(__start)

SECTIONS
{
    .text : {
        _stext = ABSOLUTE(.);
        *(.vectors)
        *(.text .text.*)
        *(.fixup)
        *(.gnu.warning)
        *(.rodata .rodata.*)
        *(.gnu.linkonce.t.*)
        *(.glue_7)
        *(.glue_7t)
        *(.got)
        *(.gcc_except_table)
        *(.gnu.linkonce.r.*)
        _etext = ABSOLUTE(.);
    } > flash

    .init_section : ALIGN(4) {
        _sinit = ABSOLUTE(.);
        KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*) SORT_BY_INIT_PRIORITY(.ctors.*)))
        KEEP(*(.init_array EXCLUDE_FILE(*crtbegin.o *crtbegin?.o *crtend.o *crtend?.o) .ctors))
        _einit = ABSOLUTE(.);
    } > flash

    .ARM.extab : ALIGN(4) {
        *(.ARM.extab*)
    } > flash

    .ARM.exidx : ALIGN(4) {
        __exidx_start = ABSOLUTE(.);
        *(.ARM.exidx*)
        __exidx_end = ABSOLUTE(.);
    } > flash

    .tdata : {
        _stdata = ABSOLUTE(.);
        *(.tdata .tdata.* .gnu.linkonce.td.*);
        _etdata = ABSOLUTE(.);
    } > flash

    .tbss : {
        _stbss = ABSOLUTE(.);
        *(.tbss .tbss.* .gnu.linkonce.tb.* .tcommon);
        _etbss = ABSOLUTE(.);
    } > flash

    _eronly = ABSOLUTE(.);

    /* The RAM vector table (if present) should lie at the beginning of SRAM */

    .ram_vectors : {
        *(.ram_vectors)
    } > sram

    .data : ALIGN(4) {
        _sdata = ABSOLUTE(.);
        *(.data .data.*)
        *(.gnu.linkonce.d.*)
        CONSTRUCTORS
        . = ALIGN(4);
        _edata = ABSOLUTE(.);
    } > sram AT > flash

    .bss : ALIGN(4) {
        _sbss = ABSOLUTE(.);
        *(.bss .bss.*)
        *(.gnu.linkonce.b.*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = ABSOLUTE(.);
    } > sram

    /* Drop the build-id / note prelude so the vector table in .text
     * sits at the start of the AP virtual partition (0x02150000).
     * orphan .note.gnu.build-id is placed first and pushes _vectors
     * at the start of the AP virtual partition (0x02150000). */

    /DISCARD/ : {
        *(.note.gnu.build-id)
        *(.note*)
    }

    /* Stabs debugging sections. */

    .stab 0 : { *(.stab) }
    .stabstr 0 : { *(.stabstr) }
    .stab.excl 0 : { *(.stab.excl) }
    .stab.exclstr 0 : { *(.stab.exclstr) }
    .stab.index 0 : { *(.stab.index) }
    .stab.indexstr 0 : { *(.stab.indexstr) }
    .comment 0 : { *(.comment) }
    .debug_abbrev 0 : { *(.debug_abbrev) }
    .debug_info 0 : { *(.debug_info) }
    .debug_line 0 : { *(.debug_line) }
    .debug_pubnames 0 : { *(.debug_pubnames) }
    .debug_aranges 0 : { *(.debug_aranges) }
}
