# 470 欢乐斗地主 — BK7258 对话式 AI 开发套件新硬件适配

## 参赛信息

| 项目 | 内容 |
| --- | --- |
| 队伍编号 | 470 |
| 队伍名称 | 欢乐斗地主 |
| 选题方向 | 新硬件适配 |
| 成员与分工 | YangMaxpro：BK7258 芯片/板级 BSP、构建烧录、真机 XTS 验证、文档和 AI Coding 材料 |
| 官方作品仓 | [`open-vela/contest2026_470_huanledoudizhu`](https://github.com/open-vela/contest2026_470_huanledoudizhu) |
| 芯片上游贡献 | [`open-vela/nuttx` PR #360](https://github.com/open-vela/nuttx/pull/360) |

## 项目定位

**项目名称：** BK7258 R1 开发套件 openvela 新硬件适配

**一句话定位：** 面向新硬件适配赛道，在 BK7258 双核 Cortex-M33F R1 开发套件上完成 openvela 芯片级 BSP、板级 BSP、启动、中断、SysTick、UART、内存与 PSRAM、Wi-Fi、NSH 及构建烧录链路适配，并通过真机 xTS 测试形成可复现的硬件适配基线；“小派”作为板级能力验证应用。

## 一、作品简介

本作品完成 **声网 & 博通集成「对话式 AI 开发套件 R1」**（Beken BK7258，ARMv8-M Cortex-M33F 双核 SoC）在 openvela 上的 BSP L0 基线，属于新硬件适配赛道。当前先打通可复现的启动、编译、应用挂载和 NSH 控制链路，再逐项接入真实外设驱动：

- 芯片层：在 `openvela/nuttx` 新增 `arch/arm/src/bk7258/` 芯片 BSP（启动、串口、SysTick 定时器、NVIC 中断管理、堆内存），已向 `open-vela/nuttx:dev-ai-contest-2026` 提交 PR #360；
- 板级层：在本仓 `board/contest_board/` 提供 BK7258 DevKit 板级配置（defconfig、Flash 链接脚本、板级初始化、board.h），以 PR #1 提交；
- 应用层：`app/hello_app/` 提供 HelloWorld 示例应用验证 NSH；`app/xiaopai/` 提供“小派”控制层，验证离线唤醒、问答、提醒状态机、worker 任务调度和可选硬件能力探测；`app/demos/` 提供 `packages/demos` 顶层聚合入口，确保这些应用进入镜像。

核心功能按硬件能力分层实现：

| 功能 | NuttX 子系统 | 当前状态 |
| ---- | ---- | ---- |
| 本地语音唤醒 | `audio` + I2S + 本地唤醒引擎 | 控制层已就绪，等待双麦克风/I2S 驱动 |
| 采集与降噪 | `audio` + BK7258 DSP 封装 | 模拟音频/PCM 诊断链路已接入；标准 audio upper-half 与 DSP 降噪待完善 |
| 云端 AI 对话 | `netdev` + TLS/HTTP 或 MQTT | CP IPC Wi-Fi netdev、DHCP、DNS 和 TLS 检查已接入；云端大模型业务协议待完成 |
| 视觉看护 | `video` + DVP/ISP | 按需能力探测，等待摄像头驱动 |
| 屏幕反馈 | `fb` + RGB LCD | 按需能力探测，等待 framebuffer 驱动 |
| LED/马达通知 | `gpio` / `pwm` | R1 红/绿 LED（GPIO40/41）已接入状态反馈；PWM/马达待驱动 |
| 多任务调度 | NuttX scheduler、消息队列 | 当前控制状态机可验证，驱动接入后拆分音频/网络/UI 任务 |

当前镜像已包含 XiaoPai 控制层、BK7258 mailbox、专用 AP PSRAM 堆、Wi-Fi netdev、TRNG 和模拟音频/PCM 诊断链路。DVP、LCD、BLE、标准 audio upper-half 与 PWM/马达仍需按 R1 原理图和厂商 SDK 继续适配。

## 二、选题方向

**新硬件适配**。开发套件 R1 基于 BK7258 芯片，当前 openvela 尚无该 SoC 支持，本作品从零完成芯片 BSP + 板级 BSP 移植，打通「拉取工程 → 编译 → 烧录 → NSH 运行」全流程，为后续对话式 AI 应用（音频链路、屏幕显示、云服务接入）奠定系统底座。

## 三、目录结构

```
├── board/contest_board/                 # BK7258 DevKit 板级 BSP
│   ├── configs/bk7258-devkit/nsh/defconfig # NSH 配置（UART0 + SysTick + 内存）
│   ├── include/board.h                   # 板级定义和 UART0 引脚
│   ├── scripts/bk7258_flash.ld           # AP Flash 链接脚本
│   ├── src/board_boot.c                  # 板级早期初始化
│   └── README.md                         # BSP 移植说明
├── app/hello_app/                        # HelloWorld 示例应用
├── app/xiaopai/                          # 小派控制层和 RTSA 适配
├── app/demos/                            # demos 顶层 CMake/Make 聚合入口
├── docs/                                 # 硬件适配报告、XTS 覆盖矩阵和测试说明
├── evidence/                             # 构建、主机测试和真机串口原始证据
│   ├── build-and-host-tests/<date>/
│   └── xts/<date>/
├── logs/                                 # AI Coding 真实会话日志
│   └── YangMaxpro/<date>/
├── skills/                               # 自建 Skill
│   ├── bk7258-openvela-development/SKILL.md
│   └── bk7258-xts-test/SKILL.md
├── tools/                                # 构建、网络、音频、RTSA 和诊断工具
│   ├── build_image/
│   ├── system/
│   ├── network/
│   ├── audio/
│   ├── rtsa/
│   └── convoai/
├── SUBMISSION_CHECKLIST.md               # 赛事提交检查表
├── openvela.xml                          # openvela 工程映射和版本固定
└── contest2026_470_huanledoudizhu.xml   # 本仓作品目录映射
```

配套提交：芯片 BSP 的上游提交为 [`open-vela/nuttx` PR #360](https://github.com/open-vela/nuttx/pull/360)。PR 合入前，本仓 `openvela.xml` 固定到 `YangMaxpro/nuttx@ebd2bba1677d695586860ee7050f987b60bdfe06` 以保证 `repo sync` 可复现；合入后应改回官方 `dev-ai-contest-2026` revision。

## 四、运行方式

```bash
# 1. 拉取 openvela 全量工程（含本专属仓）
repo init -u https://github.com/open-vela/contest2026_470_huanledoudizhu \
  -b dev-ai-contest-2026 -m contest2026_470_huanledoudizhu.xml
repo sync -c -j8
# PR #360 合入前，manifest 拉取固定的 YangMaxpro/nuttx@ebd2bba1677d

# 2. 进入 openvela 工作区根目录（本仓上一级），编译 BK7258 DevKit NSH 镜像
cd contest2026_470_huanledoudizhu/..
./build.sh contest2026_470_huanledoudizhu/board/contest_board/configs/bk7258-devkit/nsh --cmake

# 3. 产物
#    cmake_out/configs_nsh/nuttx.bin  （最近一次构建为 146560 B）
#    BK7258 UART0（GPIO11 TX / GPIO10 RX，115200 8N1）为 NSH 串口控制台
#
# 4. 烧录与运行
#
#    烧录命令参考：
#
     ./bk_loader download -p 0 -b 1500000 -s 0x11000 -i /home/yang/openvela/bk7258_package/openvela-cp-ap-update-xts-block-v27-at-0x11000.bin
#
#    BK7258 的 flash_crc_enable 配置要求 CP/AP 分区按 32+2 字节 CRC16 编码；
#    不要直接把 nuttx.bin 或未编码的 CP/AP 原始文件拼接进 8 MB Flash。
#    使用 tools/build_image/make_bk7258_linear_crc_image.py 生成镜像时保留 R1 原厂
#    bootloader，并将 OpenVela CP/AP 替换到 0x11000/0x165000：
#    python3 tools/build_image/make_bk7258_linear_crc_image.py \
#      --factory bk7258_original_8MB_backup.bin \
#      --cp app.bin --ap app1.bin --output openvela-bk7258-8MB.bin
#    BKFIL 下载握手使用 1500000；烧录完成后的 NSH 控制台使用 115200：
#    bk_loader download -p 0 -b 1500000 -s 0x0 -i openvela-bk7258-8MB.bin
#    RST 复位后若 USB 串口重新枚举，先执行 ls /dev/ttyUSB*，将 -p 改为对应端口序号
nsh> hello
nsh> help
nsh> xiaopai status
nsh> xiaopai wake
nsh> xiaopai ask hello world
nsh> xiaopai remind take medicine
nsh> xiaopai led green
nsh> xiaopai led red
nsh> xiaopai led both
nsh> xiaopai led off
nsh> xiaopai demo
```

验证结论（L0/L1 基线）：

| 项目 | 状态 |
| --- | --- |
| 编译通过（CMake，1507 targets） | ✅ |
| Flash 链接 / 向量表 / 启动入口 | ✅ `_vectors`@0x02150000，`__start`@0x02150220 |
| UART0 串口驱动 + NSH 控制台代码接入 | ✅ 编译通过；UART0 引脚/波特率已按真机 SDK 固化 |
| SysTick 系统时钟 + `up_irqinitialize` 中断初始化 | ✅ |
| 芯片 BSP 上游 PR #360 | ⚠️ 1 commit / 44 files；checkpatch 和 CLA 已通过，其余 CI 执行中，等待 code owner review |
| XiaoPai 控制层、能力探测、worker 任务编译进镜像 | ✅ |

真机记录：BKFIL 2.1.11.8 能返回 `Writing Flash OK`。使用 CRC16 编码的镜像在 BK7258 R1 上已观测到 `nsh>`，并完成 `ostest`（status 0）、`mm`（`TEST COMPLETE`）、`scanftest`（挂载 `/tmp` tmpfs 后 `OK: 164, FAILED: 0`）和 `hello` 真机验证。未编码的 CP/AP 线性镜像会在启动校验阶段失败，烧录时必须使用 CRC 编码镜像；完整测试限制和复测命令见 `docs/xts-test-evidence.md`。

## 五、AI Coding 使用说明

本作品使用 AI Coding 工具辅助完成 BK7258 芯片/板级适配、编译问题定位、串口测试排查和材料整理。真实会话日志按组委会格式保存在 `logs/YangMaxpro/`，清单见 `logs/YangMaxpro/manifest.json`；提交时保留 JSONL 原文，不使用示例占位日志。

本仓新增两个自建 Skill：`skills/bk7258-openvela-development/SKILL.md` 固化芯片/板级/应用代码归属、构建、CRC 镜像、烧录和真机验证流程；`skills/bk7258-xts-test/SKILL.md` 固化 XTS 测试的串口接管、tmpfs 前置条件、通过关键字、原始日志留存和失败记录规范。

## 六、当前验收状态

新硬件适配赛道的真机证据和限制见 [`docs/xts-test-evidence.md`](docs/xts-test-evidence.md)，与官方 35 项通用自测的逐项对照见 [`docs/xts-official-coverage.md`](docs/xts-official-coverage.md)，提交前检查项见 [`SUBMISSION_CHECKLIST.md`](SUBMISSION_CHECKLIST.md)。当前已确认 `ostest`、`mm`、`scanftest`（挂载 tmpfs 后）、`hello` 和烧写测试通过，RAM 占用统计已完成；其他项目按证据分别记录为部分完成、阻塞、未构建或未测试。

