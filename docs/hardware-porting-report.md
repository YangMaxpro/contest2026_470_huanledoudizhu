# BK7258 新硬件适配报告

本报告按官方《新硬件适配赛道详细指引》组织，目标硬件为声网 & 博通对话式 AI 开发套件 R1（Beken BK7258）。代码入口在本仓库，芯片级改动通过 manifest 固定到 `YangMaxpro/nuttx@ebd2bba1677d695586860ee7050f987b60bdfe06`，便于在上游 PR #360 合入前复现。

## 参赛信息

| 项目 | 内容 |
| --- | --- |
| 队伍编号 / 名称 | 470 / 欢乐斗地主 |
| 选题方向 | 新硬件适配 |
| 成员与分工 | YangMaxpro：BK7258 芯片/板级 BSP、构建烧录、真机 XTS 验证、文档和 AI Coding 材料 |
| 官方作品仓 | <https://github.com/open-vela/contest2026_470_huanledoudizhu> |
| 芯片上游 PR | <https://github.com/open-vela/nuttx/pull/360> |

## 1. 适配范围

| 官方要求 | 本作品实现 | 代码位置 / 证据 |
| --- | --- | --- |
| 芯片级 BSP | Cortex-M33F 启动入口、向量表、FPU、BSS/data 初始化、NVIC、SysTick、堆和 PSRAM 区域 | `nuttx/arch/arm/src/bk7258/`；`board/contest_board/README.md` |
| 板级初始化 | R1 时钟/引脚、UART0 控制台、红绿 LED、音频 PA 控制、CP/AP mailbox 启动 | `board/contest_board/src/board_boot.c`、`include/board.h` |
| 基础外设 | BK7258 UART0 寄存器级收发，115200 8N1；GPIO40/41 状态灯 | `nuttx/arch/arm/src/bk7258/bk7258_serial.c`、板级代码 |
| 构建集成 | defconfig、CMake/Make 入口、Flash 链接脚本、manifest linkfile | `board/contest_board/configs/.../defconfig`、`contest2026_470_huanledoudizhu.xml` |
| 可运行 Demo | NSH、`hello`、`xiaopai` 状态机、Wi-Fi 初始化、LED 反馈 | `app/hello_app/`、`app/xiaopai/` |

## 2. 可复现流程

```bash
repo init -u https://github.com/open-vela/contest2026_470_huanledoudizhu \
  -b dev-ai-contest-2026 -m contest2026_470_huanledoudizhu.xml
repo sync -c -j8
./build.sh contest2026_470_huanledoudizhu/board/contest_board/configs/bk7258-devkit/nsh --cmake
```

BK7258 R1 使用 UART0（GPIO11 TX、GPIO10 RX，115200 8N1）。烧录时使用保留原厂 bootloader、并按 BK7258 CRC16 格式编码的完整镜像；镜像生成和 BKFIL 命令见根目录 `README.md`。

## 3. 真机验收

设备：BK7258 R1；串口：`/dev/ttyUSB0`，115200 8N1。原始日志和通过标准见 [`xts-test-evidence.md`](xts-test-evidence.md)，35 项官方通用自测的逐项状态见 [`xts-official-coverage.md`](xts-official-coverage.md)。已确认：

- `ostest` 输出 `ostest_main: Exiting with status 0`；
- `mm` 输出 `TEST COMPLETE`；
- `scanftest` 在先执行 `mount -t tmpfs tmpfs /tmp` 后输出 `OK: 164, FAILED: 0`；
- `hello` 输出 `Hello, World!!`；
- Wi-Fi 关联、DHCP 和 NSH 网络链路已在串口日志中观察到。

`getprime` 当前只输出线程启动信息，没有完成标志，因此保留为 BLOCKED；GPIO、SPI/I2C、音频、BLE 和 LCD 需要相应外设或测试资源，未在报告中冒充已完成。

## 4. 提交与后续上游贡献

完整源码已通过 PR #2 合入官方作品仓的 `dev-ai-contest-2026` 分支，PR #4 已同步最终 NuttX 固定提交。芯片级 NuttX PR #360 已整理为 1 commit / 44 files，checkpatch 和 CLA 已通过；其余 CI 执行中，当前等待 code owner review。格式修正前后的 21 个 BK7258 对象文件可加载段哈希一致，未改变 BK7258 机器码。PR 合入后，将 `openvela.xml` 的 NuttX remote/revision 切换到官方仓对应提交。
