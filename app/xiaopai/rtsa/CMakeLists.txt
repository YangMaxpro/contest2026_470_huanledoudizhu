set(XIAOPAI_RTSA_SDK_DIR "" CACHE PATH "Audited Beken agora-iot-sdk root")
if(NOT EXISTS "${XIAOPAI_RTSA_SDK_DIR}/include/bk7258/agora_rtc_api.h")
  message(FATAL_ERROR "Set XIAOPAI_RTSA_SDK_DIR to the audited RTSA 1.9.5.7 SDK")
endif()
find_package(Python3 REQUIRED COMPONENTS Interpreter)
get_filename_component(RTSA_SOURCE_REAL "${CMAKE_CURRENT_SOURCE_DIR}" REALPATH)
get_filename_component(PROJECT_TOOLS "${RTSA_SOURCE_REAL}/../../../tools" ABSOLUTE)
string(REGEX REPLACE "gcc$" "" RTSA_TOOL_PREFIX "${CMAKE_C_COMPILER}")
if(RTSA_TOOL_PREFIX STREQUAL CMAKE_C_COMPILER)
  message(FATAL_ERROR "RTSA audit currently requires the ARM GCC toolchain")
endif()
set(RTSA_OBJ "${CMAKE_CURRENT_BINARY_DIR}/rtsa-port.o")
set(RTSA_SHIMS rtsa_sync.c rtsa_net.c rtsa_runtime.c rtsa_memory.c
               rtsa_hal_thread.c rtsa_libc.c rtsa_loopback.c rtsa_tree.c)
set(RTSA_LIBS "${XIAOPAI_RTSA_SDK_DIR}/bk7258/libs")
add_custom_command(
  OUTPUT "${RTSA_OBJ}"
  COMMAND "${Python3_EXECUTABLE}" "${PROJECT_TOOLS}/link_rtsa_port.py"
          --libs "${RTSA_LIBS}" --port "${CMAKE_CURRENT_SOURCE_DIR}"
          --nuttx "${NUTTX_DIR}" --build "${CMAKE_BINARY_DIR}"
          --tool-prefix "${RTSA_TOOL_PREFIX}" --object "${RTSA_OBJ}" --replace-object
          --report "${CMAKE_CURRENT_BINARY_DIR}/rtsa-port-link.json"
  DEPENDS ${RTSA_SHIMS} rtsa_trace.h "${PROJECT_TOOLS}/link_rtsa_port.py"
          "${CMAKE_BINARY_DIR}/include/nuttx/config.h"
          "${RTSA_LIBS}/librtsa.a" "${RTSA_LIBS}/libahpl.a" "${RTSA_LIBS}/libagora-cjson.a"
  VERBATIM)
set_source_files_properties("${RTSA_OBJ}" PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
# Only the SDK-facing translation unit uses its short-enum ABI.
set_source_files_properties(rtsa_probe_sdk.c PROPERTIES COMPILE_OPTIONS "-fshort-enums")
nuttx_add_application(
  NAME rtsa_probe
  SRCS rtsa_probe_main.c rtsa_probe_sdk.c "${RTSA_OBJ}"
  INCLUDE_DIRECTORIES "${XIAOPAI_RTSA_SDK_DIR}/include/bk7258"
  PRIORITY 90 STACKSIZE 8192)
