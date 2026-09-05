# contest_board — BK7258 DevKit 板级适配（新硬件适配赛道）

队伍：**470 · 欢乐斗地主**（2026 首届 openvela AI 硬件开发者大赛 — 新硬件适配赛道）

目标硬件：**声网 & 博通「对话式 AI 开发套件 R1」**（Beken **BK7258** 双核 SoC）

---

## 一、作品形态与目录说明

本目录是**板级适配（board porting）**形态，对应 openvela 编译树中的两块区域：

| 区域 | 源码位置 | 挂载方式 |
| ---- | -------- | -------- |
| 芯片 BSP（BK7258） | `nuttx/arch/arm/src/bk7258/` | `CONFIG_ARCH_CHIP_CUSTOM=y` + `CONFIG_ARCH_CHIP_CUSTOM_DIR="arch/arm/src/bk7258"` |
| 板级代码（本目录） | `board/contest_board/` | `CONFIG_ARCH_BOARD_CUSTOM=y` + `CONFIG_ARCH_BOARD_CUSTOM_DIR="../contest2026_470_huanledoudizhu/board/contest_board"` |

目录结构：

```text
board/contest_board/
├── Kconfig                  # 板级选项（ARCH_BOARD_BK7258_DEVKIT）
├── CMakeLists.txt           # 板级构建入口
├── include/
│   └── board.h              # 板级宏（晶振频率、UART0 引脚规划）
├── scripts/
│   └── bk7258_flash.ld      # 链接脚本（AP Flash XIP @0x02150000 + SRAM @0x28010000）
├── src/
│   ├── CMakeLists.txt       # 板级源文件 + LD_SCRIPT 传递
│   └── board_boot.c         # board_early_initialize / board_app_initialize
└── configs/
    └── bk7258-devkit/
        └── nsh/defconfig    # NSH 最小系统配置（L0 基线）
```

## 二、BK7258 硬件要点

- **CPU**：双核（AP: ARMv8-M Cortex-M33F @480MHz + CP)，NuttX 当前运行于 AP 核
- **内存**：
  - AP SRAM：336 KB @ `0x28010000`（`0x28000000-0x2800ffff` 为 AP spinlock 保留区）
  - PSRAM：8 MB @ `0x60000000`（通过 `CONFIG_MM_REGIONS=2` + `arm_addregion` 并入堆）
  - Flash：8 MB；AP 分区物理地址 `0x165000`，XIP 虚拟地址 `0x02150000`（物理地址按 `/34*32` 转换）
- **UART**（博通自研 IP，非 PL011/NS16550）：
  - 寄存器 32 位按结构体偏移（`0x10` config / `0x18` fifo_status / `0x1C` fifo_port …）
  - 时钟源 `UART_CLOCK = 26 MHz` 晶振；`baud = 26MHz / (clk_div + 1)`
  - UART0 基址 `0x44820000`，IRQ 向量 20；UART1 `0x45830000`/31；UART2 `0x45840000`/32
- **IRQ**：NVIC 64 条外设中断线（`InterruptMAX_IRQn`），`CONFIG_BK7258_NR_IRQS=80`（16 系统异常 + 64 外设）

## 三、构建方法

```bash
# 1. 拉取工程（见仓根 README）
repo init -u https://github.com/YangMaxpro/contest2026_470_huanledoudizhu -b feat/bk7258-devkit -m contest2026_470_huanledoudizhu.xml
repo sync -c -j8

# 2. 编译 BK7258 DevKit NSH 配置（CMake 模式）
cd openvela
./build.sh contest2026_470_huanledoudizhu/board/contest_board/configs/bk7258-devkit/nsh --cmake

# 产物
#   cmake_out/configs_nsh/nuttx.bin    约 143 KB（AP Flash XIP @0x02150000）
#   cmake_out/configs_nsh/nuttx.hex / System.map
```

验证基线（L0）：`#### build completed successfully ####`，链接报告 Flash 1.74%、SRAM 2.12%。

## 四、实现状态与后续计划

| 阶段 | 内容 | 状态 |
| ---- | ---- | ---- |
| L0 | 芯片 BSP 骨架 + NSH 最小系统编译通过 | ✅ 完成 |
| L0 | UART0 驱动（115200 8N1 console，寄存器级） | ✅ 编译通过；参数已按 SDK 固化 |
| L1 | 真机 bring-up：UART0 时钟门控 + GPIO mux（TX=GPIO11 / RX=GPIO10） | ✅ 代码已接入；待 AP 启动链路确认 |
| L1 | SysTick 时钟校准（480 MHz 核时钟） | ✅ 代码与链接验证；待 NSH 启动确认 |
| L2 | WiFi/蓝牙（BK7258 射频）、PSRAM 压力测试、NSH 网络栈 | 📅 规划 |

### 芯片 BSP 组成（`nuttx/arch/arm/src/bk7258/`）

| 文件 | 职责 |
| ---- | ---- |
| `Kconfig` | 芯片选项：`ARCH_CHIP_BK7258`（select M33F/FPU/MPU）、UART 0/1/2 菜单、`BK7258_NR_IRQS` |
| `CMakeLists.txt` / `Make.defs` | 源文件登记（CMake 与 make 双构建系统） |
| `bk7258_start.c` | 复位入口 `__start`：FPU 配置 → BSS 清零 → `.data` 拷贝 → 串口 → `nx_start` |
| `bk7258_irq.c` | NVIC 管理：`up_irqinitialize` / `up_enable_irq` / `up_disable_irq` / `up_prioritize_irq` / `arm_ack_irq` |
| `bk7258_serial.c` | UART 驱动（fifo 轮询 + 中断收发）与 console 注册 |
| `bk7258_allocateheap.c` | 堆初始化：SRAM 主堆 + PSRAM 第二区 |
| `bk7258_timer.c` | SysTick 系统定时器（480 MHz reload） |
| `chip.h` / `include/irq.h` | 芯片能力与中断向量号 |
| `hardware/` | 寄存器位定义（memorymap / uart） |

## 五、已知约束与踩坑记录（供后续维护）

1. **Custom chip/board 的关键布尔必须显式写入 defconfig**：vela 的 CMake 第一次解析只读取 defconfig 原文来决定 `arch/dummy`、`boards/dummy` 的 Kconfig symlink 是否创建；`savedefconfig` 生成的"最小 defconfig"会删掉 `CONFIG_ARCH_CHIP_CUSTOM=y` 等被 `select` 的项，导致重新配置失败。
2. **board Kconfig 不要加 `if` 守卫**：以 `boards/dummy/Kconfig` 方式挂载的板级 Kconfig 内选项必须全局可见，否则 defconfig 无法选中（初始模板的 `if ARCH_BOARD_CONTEST2026_470_BOARD` 守卫是"自锁"的死守卫）。
3. **`board` 库由 `boards/CMakeLists.txt` 预创建**：板级 `src/CMakeLists.txt` 只能 `target_sources(board ...)` 追加，不能再次 `nuttx_add_library(board)`。
4. **链接脚本传递**：`set_property(GLOBAL PROPERTY LD_SCRIPT ...)` 必须在板级 `src/CMakeLists.txt` 中、且所依赖的 Kconfig 项被选中时执行，否则顶层 `get_filename_component` 会因空参数报错。
5. **vela fork 移除了全局 `OK` 宏**（上游 NuttX 定义于 `errno.h`），芯片/板级代码用 `return 0` 替代。
