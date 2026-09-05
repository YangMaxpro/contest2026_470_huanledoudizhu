# 470 欢乐斗地主 — BK7258 对话式 AI 开发套件新硬件适配

## 小派项目定位

**项目名称**：基于 R1 套件的离线语音控制终端——“小派”

**一句话定位**：面向居家独居老人和儿童，提供本地离线语音唤醒，结合云端大模型完成语音问答、生活提醒和按需视觉看护，降低传统智能音箱的唤醒延迟并扩展居家陪护能力。

## 一、作品简介

本作品完成 **声网 & 博通集成「对话式 AI 开发套件 R1」**（Beken BK7258，ARMv8-M Cortex-M33F 双核 SoC）在 openvela 上的 BSP L0 基线，属于新硬件适配赛道。当前先打通可复现的启动、编译、应用挂载和 NSH 控制链路，再逐项接入真实外设驱动：

- 芯片层：在 `openvela/nuttx` 新增 `arch/arm/src/bk7258/` 芯片 BSP（启动、串口、SysTick 定时器、NVIC 中断管理、堆内存），提交在 `YangMaxpro/nuttx` 的 `feat/bk7258-chip` 分支；
- 板级层：在本仓 `board/contest_board/` 提供 BK7258 DevKit 板级配置（defconfig、Flash 链接脚本、板级初始化、board.h），以 PR #1 提交；
- 应用层：`app/hello_app/` 提供 HelloWorld 示例应用验证 NSH；`app/xiaopai/` 提供“小派”控制层，验证离线唤醒、问答、提醒状态机、worker 任务调度和可选硬件能力探测；`app/demos/` 提供 `packages/demos` 顶层聚合入口，确保这些应用进入镜像。

核心功能按硬件能力分层实现：

| 功能 | NuttX 子系统 | 当前状态 |
| ---- | ---- | ---- |
| 本地语音唤醒 | `audio` + I2S + 本地唤醒引擎 | 控制层已就绪，等待双麦克风/I2S 驱动 |
| 采集与降噪 | `audio` + BK7258 DSP 封装 | 接口已规划，等待 DSP 驱动 |
| 云端 AI 对话 | `netdev` + TLS/HTTP 或 MQTT | `xiaopai` 已预留状态路径，等待 Wi-Fi 6 驱动 |
| 视觉看护（可选） | `video` + DVP/ISP | 按需能力探测，等待摄像头驱动 |
| 屏幕反馈（可选） | `fb` + RGB LCD | 按需能力探测，等待 framebuffer 驱动 |
| LED/马达通知 | `gpio` / `pwm` | 按需能力探测，等待板级引脚确认 |
| 多任务调度 | NuttX scheduler、消息队列 | 当前控制状态机可验证，驱动接入后拆分音频/网络/UI 任务 |

最近一次干净 CMake 构建产物 `nuttx.bin` 为 146560 B（约 143.1 KiB），Flash 占用 1.75%、SRAM 占用 2.12%。当前镜像已包含 XiaoPai 控制层，但音频、Wi-Fi、DVP、LCD、PWM 仍需按 R1 原理图和厂商 SDK 完成设备驱动适配。

## 二、选题方向

**新硬件适配**。开发套件 R1 基于 BK7258 芯片，当前 openvela 尚无该 SoC 支持，本作品从零完成芯片 BSP + 板级 BSP 移植，打通「拉取工程 → 编译 → 烧录 → NSH 运行」全流程，为后续对话式 AI 应用（音频链路、屏幕显示、云服务接入）奠定系统底座。

## 三、目录结构

```
├── board/contest_board/           # BK7258 DevKit 板级 BSP（映射到 vendor/openvela/boards/contest2026_470_board）
│   ├── configs/bk7258-devkit/nsh/defconfig   # 最小 NSH 配置（BK7258 UART0 控制台 + SysTick + 2 段内存）
│   ├── include/board.h           # 板级定义（26MHz 晶振、UART0 引脚等）
│   ├── scripts/bk7258_flash.ld   # AP Flash 链接脚本（XIP @0x02150000，物理分区 0x165000）
│   ├── src/board_boot.c          # 板级早期初始化 / 应用初始化
│   ├── CMakeLists.txt            # 挂载 LD_SCRIPT 与 board 库源文件
│   └── README.md                 # BSP 移植文档（含 5 个已验证的坑）
├── app/hello_app/                # HelloWorld 示例应用（映射到 packages/demos/contest2026_470_hello_app）
├── app/xiaopai/                  # 小派控制层（映射到 packages/demos/contest2026_470_xiaopai）
├── app/demos/                    # packages/demos 顶层 CMake/Make 聚合入口
├── logs/                         # AI Coding 会话日志（QoderWork，经官方 schema 校验）
│   └── YangMaxpro/
└── contest2026_470_huanledoudizhu.xml   # 本仓作品目录 → openvela 编译树映射
```

配套提交：芯片 BSP 在 `YangMaxpro/nuttx` 的 `feat/bk7258-chip` 分支（`arch/arm/src/bk7258/`，13 个文件）；本仓 `openvela.xml` 已固定该 revision，fresh `repo sync` 可直接取得。

## 四、运行方式

```bash
# 1. 拉取 openvela 全量工程（含本专属仓）
repo init -u https://github.com/YangMaxpro/contest2026_470_huanledoudizhu \
  -b feat/bk7258-devkit -m contest2026_470_huanledoudizhu.xml
repo sync -c -j8
# manifest 会自动拉取 YangMaxpro/nuttx@feat/bk7258-chip

# 2. 进入 openvela 工作区根目录（本仓上一级），编译 BK7258 DevKit NSH 镜像
cd contest2026_470_huanledoudizhu/..
./build.sh contest2026_470_huanledoudizhu/board/contest_board/configs/bk7258-devkit/nsh --cmake

# 3. 产物
#    cmake_out/configs_nsh/nuttx.bin  （最近一次构建为 146560 B）
#    BK7258 UART0（GPIO11 TX / GPIO10 RX，115200 8N1）为 NSH 串口控制台

# 4. 烧录与运行
#    BK7258 必须使用包含原厂 bootloader/CP 和 openvela AP 的完整线性包，
#    AP 镜像写入物理 Flash 0x165000（XIP 地址 0x02150000）：
#    BKFIL 下载握手使用 1500000；烧录完成后的 NSH 控制台使用 115200：
#    bk_loader download -p 0 -b 1500000 -s 0x0 -i openvela-all-app.bin
#    RST 复位后若 USB 串口重新枚举，先执行 ls /dev/ttyUSB*，将 -p 改为对应端口序号
nsh> hello
nsh> help
nsh> xiaopai status
nsh> xiaopai wake
nsh> xiaopai ask hello world
nsh> xiaopai remind take medicine
nsh> xiaopai demo
```

验证结论（L0/L1 基线）：

| 项目 | 状态 |
| --- | --- |
| 编译通过（CMake，1099 targets） | ✅ |
| Flash 链接 / 向量表 / 启动入口 | ✅ `_vectors`@0x02150000，`__start`@0x02150220 |
| UART0 串口驱动 + NSH 控制台代码接入 | ✅ 编译通过；UART0 引脚/波特率已按真机 SDK 固化 |
| SysTick 系统时钟 + `up_irqinitialize` 中断初始化 | ✅ |
| 芯片 BSP 通过 checkpatch 与 CLA 检查 | ✅ |
| XiaoPai 控制层、能力探测、worker 任务编译进镜像 | ✅ |

真机记录：BKFIL 2.1.11.8 完整线性包在 1500000 波特率下曾返回 `Writing Flash OK`；复位后串口可见原厂 CP `$` CLI。当前记录尚未观测到 openvela `nsh>` 提示符，AP/CP 启动选择仍需在后续硬件联调中确认。因此本阶段结论是“源码已编译进镜像，烧录链路已验证，NSH 真机启动待联调”，不把预留设备节点描述为已完成驱动。

## 五、AI Coding 使用说明


