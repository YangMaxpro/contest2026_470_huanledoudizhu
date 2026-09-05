# Contest 2026 team 470 XiaoPai device service
if(CONFIG_LVX_USE_DEMO_CONTEST2026_470_XIAOPAI)
  nuttx_add_application(
    NAME xiaopai
    SRCS xiaopai_main.c
    STACKSIZE 4096)
endif()
