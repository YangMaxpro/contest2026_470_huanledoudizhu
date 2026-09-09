/****************************************************************************
 * Contest 2026 team 470 - XiaoPai device service
 *
 * This is the hardware-independent control plane for the R1 terminal.  It
 * deliberately does not pretend to implement an audio, Wi-Fi, camera or
 * display driver.  Drivers register NuttX devices or network interfaces;
 * this service discovers them and keeps the application behavior stable while
 * hardware bring-up progresses.
 ****************************************************************************/

#include <nuttx/config.h>
#include <errno.h>
#ifdef CONFIG_XIAOPAI_WIFI_PERSIST
#include "xiaopai_wifi.h"
#endif
#ifdef CONFIG_XIAOPAI_VOICE
#include "xiaopai_voice.h"
#endif
#ifdef CONFIG_BK7258_AUDIO
#include "xiaopai_audio.h"
#endif
#ifdef CONFIG_NETDEV_IFINDEX
#include <net/if.h>
#endif
#include <stdbool.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>

#include <arch/board/board.h>
#ifdef CONFIG_BK7258_MBOX_V2
#include <arch/chip/bk7258_heartbeat.h>
#endif
#ifdef CONFIG_XIAOPAI_NETWATCH
#include "xiaopai_netwatch.h"
#endif
#ifdef CONFIG_XIAOPAI_RNGCHECK
#include "xiaopai_rngcheck.h"
#endif
#ifdef CONFIG_XIAOPAI_HTTPCHECK
#include "xiaopai_httpcheck.h"
#endif

#define XIAOPAI_TEXT_MAX 96
#ifdef CONFIG_XIAOPAI_MIMO
#include "xiaopai_mimo.h"
#endif

enum xiaopai_state_e
{
  XIAOPAI_IDLE = 0,
  XIAOPAI_LISTENING,
  XIAOPAI_THINKING,
  XIAOPAI_RESPONDING,
  XIAOPAI_REMINDER
};

struct xiaopai_ctx_s
{
  enum xiaopai_state_e state;
  bool audio;
  bool network;
  bool video;
  bool display;
  bool feedback;
};

static struct xiaopai_ctx_s *g_xiaopai_worker_ctx;

static const char *xiaopai_state_name(enum xiaopai_state_e state)
{
  switch (state)
    {
      case XIAOPAI_LISTENING:
        return "listening";
      case XIAOPAI_THINKING:
        return "thinking";
      case XIAOPAI_RESPONDING:
        return "responding";
      case XIAOPAI_REMINDER:
        return "reminder";
      default:
        return "idle";
    }
}

static bool xiaopai_node_exists(const char *path)
{
  struct stat st;

  return stat(path, &st) == 0;
}

static bool xiaopai_any_node(const char *const *paths)
{
  unsigned int i;

  for (i = 0; paths[i] != NULL; i++)
    {
      if (xiaopai_node_exists(paths[i]))
        {
          return true;
        }
    }

  return false;
}

static void xiaopai_probe(struct xiaopai_ctx_s *ctx)
{
  static const char *const audio_nodes[] =
    { "/dev/audio/pcm0", "/dev/audio/pcm1", NULL };
  static const char *const video_nodes[] =
    { "/dev/video0", "/dev/video1", NULL };
  static const char *const display_nodes[] =
    { "/dev/fb0", "/dev/fb1", NULL };
  static const char *const feedback_nodes[] =
    { "/dev/pwm0", "/dev/led0", NULL };

  ctx->audio = xiaopai_any_node(audio_nodes);
#if defined(CONFIG_NETDEV_IFINDEX) && defined(CONFIG_BK7258_WIFI)
  ctx->network = if_nametoindex(CONFIG_BK7258_WIFI_IFNAME) != 0;
#else
  ctx->network = false;
#endif
  ctx->video = xiaopai_any_node(video_nodes);
  ctx->display = xiaopai_any_node(display_nodes);
  ctx->feedback = xiaopai_any_node(feedback_nodes) ||
                  bk7258_board_feedback_available();
}

static int xiaopai_join_args(int argc, char *argv[], int first,
                             char *buffer, size_t buffer_len)
{
  size_t used = 0;
  int i;

  if (buffer_len == 0)
    {
      return 0;
    }

  buffer[0] = '\0';
  for (i = first; i < argc; i++)
    {
      const char *src = argv[i];

      if (i > first && used + 1 < buffer_len)
        {
          buffer[used++] = ' ';
        }

      while (*src != '\0' && used + 1 < buffer_len)
        {
          buffer[used++] = *src++;
        }
    }

  buffer[used] = '\0';
  return (int)used;
}

static void xiaopai_print_capability(const char *name, bool available)
{
  printf("  %-12s %s\n", name, available ? "available" : "unavailable");
}

static void xiaopai_print_status(const struct xiaopai_ctx_s *ctx)
{
  printf("XiaoPai state: %s\n", xiaopai_state_name(ctx->state));
  printf("XiaoPai capabilities (device/interface registration):\n");
  xiaopai_print_capability("audio/PCM", ctx->audio);
#ifdef CONFIG_BK7258_AUDIO
  printf("  audio diagnostics: xiaopai audio (hardware verification pending)\n");
#endif
  xiaopai_print_capability("network/Wi-Fi", ctx->network);
  xiaopai_print_capability("camera/DVP", ctx->video);
  xiaopai_print_capability("display/RGB", ctx->display);
  xiaopai_print_capability("feedback/PWM", ctx->feedback);
}

static void xiaopai_print_help(void)
{
  printf("Usage: xiaopai <command> [argument]\n");
#ifdef CONFIG_XIAOPAI_WIFI_PERSIST
  printf("  wifi save <SSID>|connect|status|forget  saved Wi-Fi profile\n");
#endif
  printf("  status              probe devices and print current state\n");
#ifdef CONFIG_XIAOPAI_NETWATCH
  printf("  time status         show system clock and NTP sample state\n");
#endif
#ifdef CONFIG_BK7258_MBOX_V2
  printf("  ipc status          read heartbeat/mailbox counters\n");
#endif
#ifdef CONFIG_BK7258_AUDIO
  printf("  audio status|tone|record|play|clear  local analog audio test\n");
#endif
  printf("  netprobe            read CP Wi-Fi MAC/status over mailbox\n");
#ifdef CONFIG_XIAOPAI_NETWATCH
  printf("  netwatch start|stop|status  manage DHCP across reconnects\n");
#endif
#ifdef CONFIG_XIAOPAI_RNGCHECK
  printf("  rngcheck            check CP hardware random source\n");
#endif
#ifdef CONFIG_XIAOPAI_HTTPCHECK
  printf("  httpcheck [http://host/path]  test TCP/HTTP (no TLS)\n");
#ifdef CONFIG_XIAOPAI_HTTPSCHECK
  printf("  httpscheck [https://host/path]  verify TLS and HTTP\n");
#endif
#endif
  printf("  capabilities        print optional hardware availability\n");
#ifdef CONFIG_XIAOPAI_VOICE
  printf("  voice start [1..10]|stop|status  one Xiaomi voice turn\n");
#endif
  printf("  wake                enter local wake/listening state\n");
#ifdef CONFIG_XIAOPAI_MIMO
  printf("  ask <text>          send one real MiMo text request\n");
  printf("  cloud status|key|clear|model <name>  MiMo configuration\n");
#else
  printf("  ask <text>          test request handling (cloud not connected)\n");
#endif
  printf("  remind <text>       create a local reminder event\n");
  printf("  demo                exercise the complete control path\n");
  printf("  led <off|red|green|both>  manually test R1 status LEDs\n");
}

static int xiaopai_set_feedback(struct xiaopai_ctx_s *ctx,
                                 enum bk7258_board_feedback_e feedback)
{
  int ret;

  ret = bk7258_board_set_feedback(feedback);
  if (ret < 0)
    {
      ctx->feedback = false;
      printf("XiaoPai: board feedback unavailable (%d)\n", ret);
    }

  return ret;
}

#ifndef CONFIG_XIAOPAI_MIMO
static int xiaopai_ask(struct xiaopai_ctx_s *ctx, const char *text)
{
  if (text == NULL || text[0] == '\0')
    {
      printf("xiaopai: ask requires text\n");
      return -EINVAL;
    }

  /* NSH starts a fresh process for each command.  Treat an ask issued from
   * the idle shell as a new local wake event so the control path remains
   * usable without requiring a resident daemon during early bring-up. */

  if (ctx->state != XIAOPAI_LISTENING)
    {
      ctx->state = XIAOPAI_LISTENING;
      (void)xiaopai_set_feedback(ctx, BK7258_BOARD_FEEDBACK_LISTENING);
      printf("XiaoPai local wake accepted\n");
    }

  ctx->state = XIAOPAI_THINKING;
  (void)xiaopai_set_feedback(ctx, BK7258_BOARD_FEEDBACK_THINKING);
  printf("XiaoPai request queued: %s\n", text);

  if (!ctx->network)
    {
      ctx->state = XIAOPAI_IDLE;
      (void)xiaopai_set_feedback(ctx, BK7258_BOARD_FEEDBACK_ERROR);
      printf("XiaoPai: network unavailable; request kept local\n");
      return -ENETUNREACH;
    }

  ctx->state = XIAOPAI_RESPONDING;
  (void)xiaopai_set_feedback(ctx, BK7258_BOARD_FEEDBACK_RESPONDING);
  printf("XiaoPai: network interface registered; cloud adapter not implemented\n");
  ctx->state = XIAOPAI_IDLE;
  (void)xiaopai_set_feedback(ctx, BK7258_BOARD_FEEDBACK_OFF);
  return -ENOSYS;
}
#endif

static int xiaopai_demo_worker(int argc, char *argv[])
{
  struct xiaopai_ctx_s *ctx = g_xiaopai_worker_ctx;

  UNUSED(argc);
  UNUSED(argv);

  if (ctx == NULL)
    {
      return 1;
    }

  ctx->state = XIAOPAI_LISTENING;
  (void)xiaopai_set_feedback(ctx, BK7258_BOARD_FEEDBACK_LISTENING);
  printf("[1/4] local wake accepted (worker task)\n");
  ctx->state = XIAOPAI_THINKING;
  (void)xiaopai_set_feedback(ctx, BK7258_BOARD_FEEDBACK_THINKING);
  printf("[2/4] request classified locally (worker task)\n");
  ctx->state = XIAOPAI_RESPONDING;
  (void)xiaopai_set_feedback(ctx, BK7258_BOARD_FEEDBACK_RESPONDING);
  printf("[3/4] response path selected (local fallback)\n");
  ctx->state = XIAOPAI_REMINDER;
  (void)xiaopai_set_feedback(ctx, BK7258_BOARD_FEEDBACK_REMINDER);
  printf("[4/4] reminder/state notification committed\n");
  ctx->state = XIAOPAI_IDLE;
  (void)xiaopai_set_feedback(ctx, BK7258_BOARD_FEEDBACK_OFF);
  return 0;
}

static int xiaopai_run_demo(struct xiaopai_ctx_s *ctx)
{
  int status;
  pid_t pid;

  g_xiaopai_worker_ctx = ctx;
  pid = task_create("xiaopai_worker",
                    CONFIG_LVX_USE_DEMO_CONTEST2026_470_XIAOPAI_TASK_PRIORITY,
                    CONFIG_LVX_USE_DEMO_CONTEST2026_470_XIAOPAI_TASK_STACKSIZE,
                    xiaopai_demo_worker, NULL);
  if (pid < 0)
    {
      int errcode = errno;

      g_xiaopai_worker_ctx = NULL;
      printf("xiaopai: worker task creation failed: %d\n", errcode);
      return -errcode;
    }

  if (waitpid(pid, &status, 0) != pid)
    {
      int errcode = errno;

      g_xiaopai_worker_ctx = NULL;
      printf("xiaopai: worker task wait failed: %d\n", errcode);
      return -errcode;
    }

  g_xiaopai_worker_ctx = NULL;
  if (!WIFEXITED(status) || WEXITSTATUS(status) != 0)
    {
      printf("xiaopai: worker task exited abnormally\n");
      return -EIO;
    }

  return 0;
}

static int xiaopai_command(struct xiaopai_ctx_s *ctx, int argc,
                            char *argv[])
{
  const char *command;

  if (argc < 2)
    {
      xiaopai_print_help();
      return -EINVAL;
    }

  command = argv[1];
#ifdef CONFIG_BK7258_MBOX_V2
  if (strcmp(command, "ipc") == 0)
    {
      struct bk7258_heartbeat_status status;

      if (argc != 3 || strcmp(argv[2], "status") != 0)
        {
          printf("Usage: xiaopai ipc status\n");
          return -EINVAL;
        }

      bk7258_heartbeat_get_status(&status);
      printf("IPC v31: started=%u sending=%u attempts=%lu ack=%lu "
             "failures=%lu result=%d\n",
             status.started, status.sending, (unsigned long)status.attempts,
             (unsigned long)status.acknowledgements,
             (unsigned long)status.failures, status.last_result);
      printf("IPC ms: since_attempt=%llu since_ack=%llu max_gap=%llu "
             "max_send=%llu\n",
             (unsigned long long)status.since_attempt_ms,
             (unsigned long long)status.since_ack_ms,
             (unsigned long long)status.max_attempt_gap_ms,
             (unsigned long long)status.max_send_ms);
      printf("Mailbox: state=%u tx=%lu rx=%lu timeout=%lu bad_ack=%lu "
             "recovery=%lu down=%lu\n", status.mailbox_state,
             (unsigned long)status.mailbox_tx, (unsigned long)status.mailbox_rx,
             (unsigned long)status.mailbox_timeouts,
             (unsigned long)status.mailbox_bad_ack,
             (unsigned long)status.mailbox_recoveries,
             (unsigned long)status.mailbox_down);
      return 0;
    }
#endif
#ifdef CONFIG_XIAOPAI_RNGCHECK
  if (strcmp(command, "rngcheck") == 0)
    {
      return argc == 2 ? xiaopai_rngcheck() : -EINVAL;
    }
#endif
#ifdef CONFIG_XIAOPAI_HTTPCHECK
  if (strcmp(command, "httpcheck") == 0)
    {
      if (argc > 3)
        {
          return -EINVAL;
        }
      return xiaopai_httpcheck(argc == 3 ? argv[2] : "http://example.com/");
    }
#endif
#ifdef CONFIG_BK7258_AUDIO
  if (strcmp(command, "audio") == 0)
    {
      return xiaopai_audio(argc, argv);
    }
#endif

#ifdef CONFIG_XIAOPAI_VOICE
  if (strcmp(command, "voice") == 0)
    return xiaopai_voice(argc - 2, argv + 2);
#endif
  if (strcmp(command, "netprobe") == 0)
    {
      return bk7258_wifi_probe();
    }

#ifdef CONFIG_XIAOPAI_NETWATCH
  if (strcmp(command, "time") == 0)
    {
      if (argc != 3 || strcmp(argv[2], "status") != 0)
        return -EINVAL;
      return xiaopai_time_status();
    }
#endif

#ifdef CONFIG_XIAOPAI_NETWATCH
  if (strcmp(command, "netwatch") == 0)
    {
      if (argc != 3)
        {
          printf("Usage: xiaopai netwatch start|stop|status\n");
          return -EINVAL;
        }
      return xiaopai_netwatch(argv[2]);
    }
#endif

#ifdef CONFIG_XIAOPAI_WIFI_PERSIST
  if (strcmp(command, "wifi") == 0)
    return xiaopai_wifi(argc - 2, argv + 2);
#endif

#ifdef CONFIG_XIAOPAI_HTTPSCHECK
  if (strcmp(command, "httpscheck") == 0)
    {
      if (argc > 3)
        return -EINVAL;
      return xiaopai_httpscheck(argc == 3 ? argv[2] :
        "https://valid-isrgrootx1.letsencrypt.org/");
    }
#endif

  if (strcmp(command, "status") == 0 ||
      strcmp(command, "capabilities") == 0)
    {
      xiaopai_probe(ctx);
      xiaopai_print_status(ctx);
      return 0;
    }

  if (strcmp(command, "wake") == 0)
    {
      xiaopai_probe(ctx);
      ctx->state = XIAOPAI_LISTENING;
      (void)xiaopai_set_feedback(ctx, BK7258_BOARD_FEEDBACK_LISTENING);
      printf("XiaoPai wake accepted; listening locally\n");
      if (!ctx->audio)
        {
          printf("XiaoPai: audio/I2S driver is not registered\n");
        }
      return 0;
    }

  if (strcmp(command, "ask") == 0)
    {
#ifdef CONFIG_XIAOPAI_MIMO
      int ret;
      (void)xiaopai_set_feedback(ctx, BK7258_BOARD_FEEDBACK_THINKING);
      ret = xiaopai_mimo_ask(argc - 2, argv + 2);
      (void)xiaopai_set_feedback(ctx, ret == 0 ? BK7258_BOARD_FEEDBACK_OFF :
                                BK7258_BOARD_FEEDBACK_ERROR);
      return ret;
#else
      char text[XIAOPAI_TEXT_MAX];

      if (xiaopai_join_args(argc, argv, 2, text, sizeof(text)) == 0)
        {
          return xiaopai_ask(ctx, NULL);
        }

      return xiaopai_ask(ctx, text);
#endif
    }

#ifdef CONFIG_XIAOPAI_MIMO
  if (strcmp(command, "cloud") == 0)
    return xiaopai_cloud(argc - 2, argv + 2);
#endif

  if (strcmp(command, "remind") == 0)
    {
      char text[XIAOPAI_TEXT_MAX];

      if (xiaopai_join_args(argc, argv, 2, text, sizeof(text)) == 0)
        {
          printf("xiaopai: remind requires text\n");
          return -EINVAL;
        }

      ctx->state = XIAOPAI_REMINDER;
      (void)xiaopai_set_feedback(ctx, BK7258_BOARD_FEEDBACK_REMINDER);
      printf("XiaoPai reminder stored: %s\n", text);
      ctx->state = XIAOPAI_IDLE;
      (void)xiaopai_set_feedback(ctx, BK7258_BOARD_FEEDBACK_OFF);
      return 0;
    }

  if (strcmp(command, "led") == 0)
    {
      const char *mode = argc > 2 ? argv[2] : "off";
      bool red = false;
      bool green = false;

      if (strcmp(mode, "red") == 0)
        {
          red = true;
        }
      else if (strcmp(mode, "green") == 0)
        {
          green = true;
        }
      else if (strcmp(mode, "both") == 0)
        {
          red = true;
          green = true;
        }
      else if (strcmp(mode, "off") != 0)
        {
          printf("xiaopai: led expects off, red, green or both\n");
          return -EINVAL;
        }

      if (bk7258_board_set_led(0, red) < 0 ||
          bk7258_board_set_led(1, green) < 0)
        {
          printf("xiaopai: LED write failed\n");
          return -EIO;
        }

      printf("XiaoPai LEDs: red=%s green=%s\n",
             red ? "on" : "off", green ? "on" : "off");
      return 0;
    }

  if (strcmp(command, "demo") == 0)
    {
      xiaopai_probe(ctx);
      return xiaopai_run_demo(ctx);
    }

  if (strcmp(command, "help") == 0)
    {
      xiaopai_print_help();
      return 0;
    }

  printf("xiaopai: unknown command '%s'\n", command);
  xiaopai_print_help();
  return -EINVAL;
}

int main(int argc, char *argv[])
{
  struct xiaopai_ctx_s ctx =
    {
      .state = XIAOPAI_IDLE,
    };

  return xiaopai_command(&ctx, argc, argv);
}
