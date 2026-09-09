############################################################################
# Contest 2026 team 470 XiaoPai device service
############################################################################

include $(APPDIR)/Make.defs

ifeq ($(CONFIG_XIAOPAI_RTSA_PROBE),y)
$(error RTSA probe requires the isolated CMake build; not supported by this Makefile)
endif

ifeq ($(CONFIG_LVX_USE_DEMO_CONTEST2026_470_XIAOPAI),y)

PROGNAME  = xiaopai
PRIORITY  = 100
STACKSIZE = 8192
MODULE    = $(CONFIG_LVX_USE_DEMO_CONTEST2026_470_XIAOPAI)

MAINSRC = xiaopai_main.c
ifeq ($(CONFIG_XIAOPAI_WIFI_PERSIST),y)
CSRCS += xiaopai_wifi.c
endif
ifeq ($(CONFIG_XIAOPAI_VOICE),y)
CSRCS += xiaopai_voice.c
endif
ifeq ($(CONFIG_BK7258_AUDIO),y)
CSRCS += xiaopai_audio.c
endif
ifeq ($(CONFIG_XIAOPAI_MIMO),y)
CSRCS += xiaopai_mimo.c
endif
ifeq ($(CONFIG_XIAOPAI_NETWATCH),y)
CSRCS += xiaopai_netwatch.c
endif
ifeq ($(CONFIG_XIAOPAI_RNGCHECK),y)
CSRCS += xiaopai_rngcheck.c
endif
ifeq ($(CONFIG_XIAOPAI_HTTPCHECK),y)
CSRCS += xiaopai_httpcheck.c
endif
ifeq ($(CONFIG_XIAOPAI_HTTPSCHECK),y)
CSRCS += xiaopai_tls.c
endif

include $(APPDIR)/Application.mk

endif
