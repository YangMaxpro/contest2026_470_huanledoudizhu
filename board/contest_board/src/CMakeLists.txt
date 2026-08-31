# Contest 2026 team 470 - BK7258 DevKit board sources
#
# The `board` library itself is created by boards/CMakeLists.txt
# (nuttx_add_kernel_library(board dummy.c)), so here we only add our
# sources to that existing target.

target_sources(board PRIVATE board_boot.c)

if(CONFIG_ARCH_BOARD_BK7258_DEVKIT)
  set_property(GLOBAL PROPERTY LD_SCRIPT "${NUTTX_BOARD_DIR}/scripts/bk7258_flash.ld")
endif()
