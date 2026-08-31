# 470 欢乐斗地主 — BK7258 对话式 AI 开发套件新硬件适配

## 一、作品简介

本作品完成 **声网 & 博通集成「对话式 AI 开发套件 R1」**（Beken BK7258，ARMv8-M Cortex-M33F 双核 SoC）在 openvela 上的完整 BSP 移植，属于新硬件适配赛道。作品以「最小 NSH 基线」为目标：

- 芯片层：在 `openvela/nuttx` 新增 `arch/arm/src/bk7258/` 芯片 BSP（启动、串口、SysTick 定时器、NVIC 中断管理、堆内存），以 PR #360 提交；
- 板级层：在本仓 `board/contest_board/` 提供 BK7258 DevKit 板级配置（defconfig、Flash 链接脚本、板级初始化、board.h），以 PR #1 提交；
- 应用层：`app/hello_app/` 提供 HelloWorld 示例应用验证 NSH 与任务调度。

编译产物 `nuttx.bin` 146KB，Flash 占用 1.74%、SRAM 占用 2.12%，为后续音频编解码、对话引擎等 AI 能力预留了充足资源。

## 二、选题方向

**新硬件适配**。开发套件 R1 基于 BK7258 芯片，当前 openvela 尚无该 SoC 支持，本作品从零完成芯片 BSP + 板级 BSP 移植，打通「拉取工程 → 编译 → 烧录 → NSH 运行」全流程，为后续对话式 AI 应用（音频链路、屏幕显示、云服务接入）奠定系统底座。

## 三、目录结构

```
├── board/contest_board/           # BK7258 DevKit 板级 BSP（映射到 vendor/openvela/boards/contest2026_470_board）
│   ├── configs/bk7258-devkit/nsh/defconfig   # 最小 NSH 配置（BK7258 UART0 控制台 + SysTick + 2 段内存）
│   ├── include/board.h           # 板级定义（26MHz 晶振、UART0 引脚等）
│   ├── scripts/bk7258_flash.ld   # Flash 链接脚本（0x02000000 起，vector table @0x02000200）
│   ├── src/board_boot.c          # 板级早期初始化 / 应用初始化
│   ├── CMakeLists.txt            # 挂载 LD_SCRIPT 与 board 库源文件
│   └── README.md                 # BSP 移植文档（含 5 个已验证的坑）
├── app/hello_app/                # HelloWorld 示例应用（映射到 packages/demos/contest2026_470_hello_app）
├── logs/                         # AI Coding 会话日志（QoderWork，经官方 schema 校验）
│   └── YangMaxpro/
└── contest2026_470_huanledoudizhu.xml   # 本仓作品目录 → openvela 编译树映射
```

配套提交：芯片 BSP 在 `open-vela/nuttx` PR #360（`arch/arm/src/bk7258/`，13 个文件）。

## 四、运行方式

```bash
# 1. 拉取 openvela 全量工程（含本专属仓）
repo init -u https://github.com/open-vela/contest2026_470_huanledoudizhu \
  -b dev-ai-contest-2026 -m contest2026_470_huanledoudizhu.xml
repo sync -c -j8

# 2. 进入 openvela 工作区根目录（本仓上一级），编译 BK7258 DevKit NSH 镜像
cd contest2026_470_huanledoudizhu/..
./build.sh contest2026_470_huanledoudizhu/board/contest_board/configs/bk7258-devkit/nsh --cmake

# 3. 产物
#    out/contest2026_470_huanledoudizhu/bk7258-devkit/nsh/nuttx.bin  （146KB）
#    BK7258 UART0（Pin1 TX / Pin2 RX，1.5Mbps 默认）为 NSH 串口控制台

# 4. 烧录与运行
#    按开发套件 R1 的烧录指引将 nuttx.bin 写入 Flash（0x02000200 向量表基址），
#    复位后可在串口控制台进入 NuttShell：
nsh> hello
nsh> help
```

验证结论（L0/L1 基线）：

| 项目 | 状态 |
| --- | --- |
| 编译通过（CMake，1099 targets） | ✅ |
| Flash 链接 / 向量表 / 启动入口 | ✅ `_vectors`@0x02000200，`__start`@0x02000340 |
| UART0 串口驱动 + NSH 控制台 | ✅ |
| SysTick 系统时钟 + `up_irqinitialize` 中断初始化 | ✅ |
| 芯片 BSP 通过 checkpatch 与 CLA 检查 | ✅ |

## 五、AI Coding 使用说明

本作品的完整开发过程由 **QoderWork** 桌面智能体辅助完成，全程对话记录见 `logs/` 目录（经组委会 `validate-log.py` 官方校验通过，2170 个事件）：

- **需求拆解**：从大赛支持硬件清单中定位开发套件 R1，结合 BK7258 数据手册梳理内存布局（0x02000000 Flash / 0x28000000 PSRAM）、外设（UART0 基址 0x46000000）、中断控制器（ARMv8-M NVIC）与参考实现（mps2-an521 / rtl8720c）；
- **方案设计**：确定「custom chip + custom board」挂载路线，分析 CMake 首次解析只读 defconfig 的机制，明确 29 行最小配置的显式写法；
- **编码**：生成芯片 BSP 13 个文件与板级 BSP 全部代码，修复 8 轮编译/链接错误（含 vela fork 移除全局 `OK` 宏、`board` 库 target 冲突、LD_SCRIPT 传递等关键坑）；
- **调试**：通过 `.config` 与反汇编核对启动向量、时钟初始化与中断表；
- **文档**：产出 BSP 移植文档（board/contest_board/README.md），沉淀 5 个已验证的移植坑位。

AI 协作显著缩短了从零移植 SoC 的周期，将数据手册解读、参考代码检索、错误修复等环节的效率提升了数倍；日志中完整记录了每一轮「问题 → 分析 → 修复 → 验证」的闭环过程。
