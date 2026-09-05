# Contest 2026 team 470 package demos entry point.
#
# The upstream packages/demos project contains only demo directories.  This
# entry point is supplied by the team manifest so NuttX's recursive CMake and
# Kconfig discovery visits those linked applications.

nuttx_add_subdirectory()
nuttx_generate_kconfig(MENUDESC "Contest demos")
