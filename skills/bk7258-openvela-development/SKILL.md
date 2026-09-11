---
name: bk7258-openvela-development
description: Develop and review BK7258 support for openvela, including chip BSP, board BSP, CP/AP integration, build configuration, CRC image packaging, and hardware validation. Use for BK7258 适配、新硬件适配、BSP 开发、驱动开发、编译烧录 or bring-up work in this project.
---

# BK7258 openvela 适配开发

为 BK7258 R1 开发套件实现可复现、可上游审查的 openvela 适配。先确认代码归属和当前基线，再修改、构建、打包和验证；没有真机证据的能力不得写成已经完成。

## 触发词

- `BK7258 适配`、`新硬件适配`、`BSP 开发`
- `BK7258 驱动`、`CP/AP`、`mailbox`、`PSRAM`
- `openvela 编译`、`BKFIL 烧录`、`CRC 镜像`
- `bring-up`、`启动失败`、`NSH 无输出`、`真机回归`

## 先读项目状态

1. 读取根目录 `README.md`、`SUBMISSION_CHECKLIST.md` 和 `docs/hardware-porting-report.md`。
2. 读取 `openvela.xml`，以其中固定的 NuttX revision 为可复现基线；不要根据本地浮动分支猜测基线。
3. 涉及板级配置时读取 `board/contest_board/README.md` 和目标 `defconfig`。
4. 涉及测试结论时读取 `docs/xts-official-coverage.md` 与 `docs/xts-test-evidence.md`。

## 代码归属

- 芯片通用实现放在 NuttX `arch/arm/src/bk7258/`：启动、向量、中断、定时器、串口、堆、PSRAM、mailbox 和芯片外设。
- R1 板级实现放在 `board/contest_board/`：引脚、时钟、Flash 布局、链接脚本、板级初始化和 `defconfig`。
- 产品或诊断功能放在 `app/xiaopai/`；HelloWorld 验证放在 `app/hello_app/`。
- 可重复执行的配置、镜像和审计逻辑放在 `tools/`。不要把开发机绝对路径写进源码或提交文档。
- 芯片层改动进入 NuttX 上游 PR；赛事作品仓通过 `openvela.xml` 固定对应提交，不复制一份失去来源关系的芯片 BSP。

## 操作步骤

1. 明确问题的可观察现象、涉及的核、外设、固件版本和通过条件。保存修改前的提交号与相关日志。
2. 从启动顺序和所有权边界定位问题。CP/AP mailbox 的命令结构、长度、状态码和生命周期必须与对端一致；修改协议时同时核对发送端和接收端。
3. 做最小范围修改，并同步更新相关 Kconfig、CMake、Make、头文件或 manifest。密钥、Wi-Fi 密码和 Token 不得写入源码、普通配置、串口日志或 AI Coding 日志。
4. 使用项目 README 中的当前命令构建目标配置。记录完整命令、返回码、产物路径、源码提交和 SHA256；警告不能在报告中写成通过。
5. 按 `tools/build_image/make_bk7258_linear_crc_image.py` 的流程生成烧录镜像。保留原厂 bootloader 和未修改分区，CP/AP 数据按 BK7258 的 32+2 字节 CRC16 格式编码；不要把原始 `nuttx.bin` 直接当完整 Flash 镜像烧录。
6. 烧录前关闭占用串口的 miniterm、screen 或其他进程。BKFIL 下载和 NSH 控制台使用各自文档规定的波特率；USB 串口重新枚举后重新确认设备名。
7. 真机验证至少覆盖：复位进入 `NuttShell (NSH)`、目标命令的成功输出、`free` 前后数据、相关失败路径以及一次复位后的重复验证。运行官方 XTS 时使用 `skills/bk7258-xts-test/SKILL.md`。
8. 将原始构建日志放入 `evidence/build-and-host-tests/<date>/`，原始串口日志放入 `evidence/xts/<date>/`。更新覆盖矩阵时只依据已保存的输出。
9. 修改完成后检查 `git diff`，运行项目已有的针对性测试和格式检查。保留已知限制、待上游项和所需外设，不用相近测试替代官方用例。

## 必须保持的约束

- AP XIP、物理 Flash 分区和链接地址以当前板级 README、链接脚本与打包工具为准，三者必须一致。
- 早期启动代码不得依赖尚未初始化的堆、调度器或普通中断服务。
- mailbox、heartbeat、PWC 和控制台并发时，任何日志或网络失败都不得无限阻塞系统关键路径。
- PSRAM 初始化失败必须有可见错误和受控降级；不能注册一个实际不可用的堆。
- 基础 UART 控制台可用不能替代独立 UART 驱动回环测试；软件 watchdog 或 POSIX timer 也不能替代对应硬件驱动测试。

## 输出规范

每次开发结果应提供：

- 目标和修改前现象；
- 修改文件及其所属层级：芯片、板级、应用或工具；
- 构建命令、返回结果、产物路径和 SHA256；
- 烧录镜像组成、分区偏移和是否保留原厂区域；
- 真机命令、关键输出、原始日志路径和 PASS/FAIL/BLOCKED；
- 已知限制、未测试项目、所需外设和下一步；
- 对应作品仓提交或 NuttX PR。未提交时明确写“仅本地修改，等待本人检查”。

