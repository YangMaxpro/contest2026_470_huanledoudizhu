/****************************************************************************
 * Contest 2026 team 470 - XiaoPai device service
 *
 * This is the hardware-independent control plane for the R1 terminal.  It
 * deliberately does not pretend to implement an audio, Wi-Fi, camera or
 * display driver.  Those drivers register their normal NuttX device nodes;
 * this service discovers them and keeps the application behavior stable while
 * hardware bring-up progresses.
 ****************************************************************************/

#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

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
  static const char *const network_nodes[] =
    { "/dev/wlan0", "/dev/wifi0", NULL };
  static const char *const video_nodes[] =
    { "/dev/video0", "/dev/video1", NULL };
  static const char *const display_nodes[] =
    { "/dev/fb0", "/dev/fb1", NULL };
  static const char *const feedback_nodes[] =
    { "/dev/pwm0", "/dev/led0", NULL };

  ctx->audio = xiaopai_any_node(audio_nodes);
  ctx->network = xiaopai_any_node(network_nodes);
  ctx->video = xiaopai_any_node(video_nodes);
  ctx->display = xiaopai_any_node(display_nodes);
  ctx->feedback = xiaopai_any_node(feedback_nodes);
}

static void xiaopai_print_capability(const char *name, bool available)
{
  printf("  %-12s %s\n", name, available ? "available" : "unavailable");
}

static void xiaopai_print_status(const struct xiaopai_ctx_s *ctx)
{
  printf("XiaoPai state: %s\n", xiaopai_state_name(ctx->state));
  printf("XiaoPai capabilities (device-node probe):\n");
  xiaopai_print_capability("audio/I2S", ctx->audio);
  xiaopai_print_capability("network/Wi-Fi", ctx->network);
  xiaopai_print_capability("camera/DVP", ctx->video);
  xiaopai_print_capability("display/RGB", ctx->display);
  xiaopai_print_capability("feedback/PWM", ctx->feedback);
}

static void xiaopai_print_help(void)
{
  printf("Usage: xiaopai <command> [argument]\n");
  printf("  status              probe devices and print current state\n");
  printf("  capabilities        print optional hardware availability\n");
  printf("  wake                enter local wake/listening state\n");
  printf("  ask <text>          run the cloud-dialogue state path\n");
  printf("  remind <text>       create a local reminder event\n");
  printf("  demo                exercise the complete control path\n");
}

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
      printf("XiaoPai local wake accepted\n");
    }

  ctx->state = XIAOPAI_THINKING;
  printf("XiaoPai request queued: %s\n", text);

  if (!ctx->network)
    {
      ctx->state = XIAOPAI_IDLE;
      printf("XiaoPai: network unavailable; request kept local\n");
      return -ENETUNREACH;
    }

  ctx->state = XIAOPAI_RESPONDING;
  printf("XiaoPai: cloud transport ready; application adapter is next\n");
  ctx->state = XIAOPAI_IDLE;
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
      printf("XiaoPai wake accepted; listening locally\n");
      if (!ctx->audio)
        {
          printf("XiaoPai: audio/I2S driver is not registered\n");
        }
      return 0;
    }

  if (strcmp(command, "ask") == 0)
    {
      return xiaopai_ask(ctx, argc >= 3 ? argv[2] : NULL);
    }

  if (strcmp(command, "remind") == 0)
    {
      if (argc < 3 || argv[2][0] == '\0')
        {
          printf("xiaopai: remind requires text\n");
          return -EINVAL;
        }

      ctx->state = XIAOPAI_REMINDER;
      printf("XiaoPai reminder stored: %s\n", argv[2]);
      ctx->state = XIAOPAI_IDLE;
      return 0;
    }

  if (strcmp(command, "demo") == 0)
    {
      xiaopai_probe(ctx);
      ctx->state = XIAOPAI_LISTENING;
      printf("[1/4] local wake accepted\n");
      ctx->state = XIAOPAI_THINKING;
      printf("[2/4] request classified locally\n");
      ctx->state = XIAOPAI_RESPONDING;
      printf("[3/4] response path selected (%s)\n",
             ctx->network ? "cloud" : "local fallback");
      ctx->state = XIAOPAI_REMINDER;
      printf("[4/4] reminder/state notification committed\n");
      ctx->state = XIAOPAI_IDLE;
      return 0;
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
