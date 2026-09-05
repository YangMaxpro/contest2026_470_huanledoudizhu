# 小派设备服务（XiaoPai）

`xiaopai` 是 R1 套件离线语音控制终端的硬件无关控制层。它把本地唤醒、语音问答、提醒和状态反馈统一为一个可测试的状态机，并通过标准 NuttX 设备节点发现底层能力。

## 当前命令

在 NSH 中执行：

```text
xiaopai status
xiaopai wake
xiaopai ask "现在几点"
xiaopai remind "吃药"
xiaopai demo
```

`status` 会探测以下节点：

| 能力 | NuttX 节点 | 当前状态 |
| ---- | ---- | ---- |
| 双麦克风/I2S | `/dev/audio/pcm0` | 依赖 BK7258 I2S/DSP 驱动 |
| Wi-Fi 6 | `/dev/wlan0` | 依赖 BK7258 netdev 驱动 |
| DVP/ISP 摄像头 | `/dev/video0` | 可选，依赖 video 驱动 |
| RGB LCD | `/dev/fb0` | 可选，依赖 framebuffer 驱动 |
| LED/马达 | `/dev/pwm0` 或 `/dev/led0` | 依赖 PWM/LED 驱动 |

未注册设备节点时，命令仍可执行本地状态流转，并明确显示 `unavailable`；这让 BSP 可以先通过 NSH 验证，再逐项接入真实硬件。

`demo` 会创建一个名为 `xiaopai_worker` 的 NuttX 任务，依次执行唤醒、请求分类、响应路径选择和提醒状态提交，然后由命令进程回收任务。worker 的优先级和栈大小可通过以下 Kconfig 项调整：

```text
CONFIG_LVX_USE_DEMO_CONTEST2026_470_XIAOPAI_TASK_PRIORITY=110
CONFIG_LVX_USE_DEMO_CONTEST2026_470_XIAOPAI_TASK_STACKSIZE=3072
```

`ask` 和 `remind` 支持多个参数拼接成一条文本，最大长度为 96 字节；超过长度时会截断，避免在早期 bring-up 阶段引入动态内存分配。

## 分阶段实现

1. **L0（已接入）**：BK7258 启动、UART0/NSH、状态机、能力探测、提醒事件和 worker 任务验证。
2. **L1**：接入 BK7258 I2S 双麦克风、GPIO/PWM，并把本地唤醒词引擎放在音频采集任务上；唤醒和录音必须在本地完成，不能依赖云端。
3. **L2**：接入 Wi-Fi netdev 和 HTTPS/MQTT 云端适配器；网络任务与音频任务分离，使用队列传递压缩后的语音帧。
4. **L3（可选）**：接入 DVP/ISP 和 RGB LCD。视觉帧采用低帧率、事件触发上传，默认关闭持续视频，控制功耗和隐私风险。

## 优化约束

- 本地唤醒、降噪和离线兜底优先，网络只负责非实时问答。
- 音频采集、网络传输、UI/反馈分成独立任务，避免云端超时阻塞采集。
- 视觉默认按需启用，不在待机状态持续采集。
- 所有能力通过设备节点探测，驱动缺失时不影响 NSH 和其他功能启动。
