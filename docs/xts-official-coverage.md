# BK7258 官方 xTS 自测覆盖矩阵

对照基线：[openvela xTS 认证测试用例精简集](https://github.com/open-vela/docs/blob/dev/zh-cn/test_dev_guide/openvela_xts_test_cases.md)，核对日期：2026-09-09。

本轮串口结果由本人确认为 v16 固件输出；固件文件名和 SHA256 尚未随日志保存。判定只依据已经保存的 BK7258 真机输出。测试仅启动、只出现中间输出、或 `ostest` 内部包含同名子测试，均不算对应的独立官方用例通过。关键原文见 [`serial-key-results.log`](../evidence/xts/2026-09-09/serial-key-results.log)。

## 要求层级

需要区分比赛参赛要求和 xTS 自测要求：

| 要求来源 | 是否必须 | 本作品对应内容 |
| --- | --- | --- |
| 新硬件适配赛道参赛要求 | 必须 | 完成 openvela 系统移植，至少提供 UART 控制台，使系统正常运行；提交 defconfig、板级初始化和必要驱动源码 |
| xTS 通用自测 | 必须 | 官方 xTS 文档明确写明“通用自测用例为必测项”，共 35 项 |
| xTS 品类自测 | 按能力选测 | 根据作品实际声明的 Wi-Fi、文件系统、GPIO、Audio 等能力选择；未适配的 BLE、LCD、Camera 可注明不适用或尚未实现 |

本作品已经满足新硬件适配赛道的基础参赛要求。若要声明完成官方 xTS 通用自测，则下列 35 项都需要执行；不适配的项目应记录具体原因，不能直接计为 PASS。

### 35 项通用必测分组

| 分组 | 必测数量 | 当前完整完成 | 当前未完整完成 |
| --- | ---: | ---: | ---: |
| 1.1 系统内核 | 13 | 4 | 9 |
| 1.2 系统应用 | 4 | 1 | 3 |
| 1.3 驱动 BSP | 15 | 1 | 14 |
| 2.1 启动性能 | 2 | 0 | 2 |
| 3.1 稳定性 | 1 | 0 | 1 |
| 合计 | 35 | 6 | 29 |

“完整完成”包括 5 项 PASS 和 1 项 RAM 资源统计 COMPLETE。PARTIAL、BLOCKED、NOT BUILT 和 NOT TESTED 均计入尚未完整完成。

## 结果概览

官方文档共有 35 项通用自测条目。文档编号跳过 `1.3.8` 和 `1.3.9`，不是本表漏项。

| 状态 | 数量 | 含义 |
| --- | ---: | --- |
| PASS | 5 | 已达到官方通过条件并有真机证据 |
| COMPLETE | 1 | 资源统计类条目已采集，不是 PASS/FAIL 型测试 |
| PARTIAL | 2 | 已观察到部分结果，但证据未覆盖完整验收条件 |
| BLOCKED | 1 | 已运行，未出现官方完成标志或未返回 shell |
| NOT BUILT | 3 | 当前 XTS 镜像没有对应命令 |
| NOT TESTED | 23 | 没有按官方步骤执行和留存完整结果 |

当前可以对外声明的完整结果是：`ostest`、`mm`、`scanftest`、`hello`、烧写测试通过，RAM 占用统计已完成。不能把 `ostest` 内部的 watchdog、POSIX timer、scheduler lock 等子测试写成独立驱动用例通过。

## 1.1 系统内核（13 项）

| 编号 | 官方用例 / 命令 | 状态 | 当前证据或缺口 |
| --- | --- | --- | --- |
| 1.1.1 | 系统内存管理 / `cmocka_mm_test` | NOT BUILT | 命令未出现在当前 XTS 镜像的 `help` 列表，需要修复配置依赖并重编译 |
| 1.1.2 | 系统调度 / `cmocka_sched_test` | NOT BUILT | 同上 |
| 1.1.3 | 系统调用 / `cmocka_syscall_test` | NOT BUILT | 同上 |
| 1.1.4 | Kernel ostest / `ostest` | PASS | 最终输出 `ostest_main: Exiting with status 0` |
| 1.1.5 | Kernel getprime / `getprime` | BLOCKED | 只到 `thread #0 started...`，没有 `getprime took xxx msec`，也没有返回 `nsh>` |
| 1.1.6 | Kernel mm / `mm` | PASS | 最终输出 `TEST COMPLETE` |
| 1.1.7 | Kernel scanftest / `scanftest` | PASS | 先挂载 `/tmp` tmpfs，最终输出 `OK: 164, FAILED: 0` |
| 1.1.8 | Kernel C / `hello` | PASS | 输出 `Hello, World!!` |
| 1.1.9 | Kernel Cxx / `helloxx` | NOT TESTED | 需要看到 `CHelloWorld::HelloWorld` |
| 1.1.10 | Kernel popen / `popen` | NOT TESTED | 需要看到 `Calling pclose()`；当前配置是否包含命令待确认 |
| 1.1.11 | Kernel pipe / `pipe` | NOT TESTED | 需要看到 `Returning success`，并按文档清理 FIFO |
| 1.1.12 | Kernel MD5 / `md5_test` | NOT TESTED | 需要准备 `/etc/1.txt`，连续计算 100 次并确认结果一致 |
| 1.1.13 | Kernel C++ / `cxxtest` | NOT TESTED | 需要完整执行 vector、string、map、RTTI 等输出 |

## 1.2 系统应用（4 项）

| 编号 | 官方用例 | 状态 | 当前证据或缺口 |
| --- | --- | --- | --- |
| 1.2.1 | Reboot 启动异常 | NOT TESTED | 需执行 `reboot`，保存从 `reboot` 到 `NuttShell (NSH)` 的完整无异常日志 |
| 1.2.2 | Cold boot 启动异常 | PARTIAL | 已多次观察到复位后进入 NSH；尚未按该条目保存一次明确的按键复位完整日志并确认全程无 error |
| 1.2.3 | 系统 RAM 占用统计 / `free` | COMPLETE | 已记录 AP PSRAM 和 Umem 的 total/used/free 等数据 |
| 1.2.4 | 系统 Flash 占用统计 / `df -h` | PARTIAL | 已执行，但只显示 `/proc`；没有可统计的实际 Flash 文件系统或厂商 Flash 分区占用表 |

## 1.3 驱动 BSP（15 项）

| 编号 | 官方用例 / 命令 | 状态 | 当前证据或缺口 |
| --- | --- | --- | --- |
| 1.3.1 | 烧写测试 | PASS | BKFIL 输出 `Writing Flash OK`，复位后进入 `NuttShell (NSH)` |
| 1.3.2 | RAM 读写 / `fstest -n 10 -m /tmp` | NOT TESTED | `/tmp` 可挂载 tmpfs，但尚未执行 `fstest` |
| 1.3.3 | RAM 读写性能 / `ramtest` | NOT TESTED | 尚未按 `free` 的最大空闲块选择 size 并执行 |
| 1.3.4 | RAM 随机读写 / `cmocka_driver_block` | NOT TESTED | 需 RAM block 设备、`mkrd` 和 driver test 配置 |
| 1.3.5 | Flash 功能 / `cmocka_driver_block` | NOT TESTED | 需注册可测试的 Flash block 设备，不能用烧写成功替代 |
| 1.3.6 | GPIO / `cmocka_driver_gpio` | NOT TESTED | 当前 LED GPIO 工作不等于 GPIO0/GPIO1 杜邦线回环测试通过 |
| 1.3.7 | I2C/SPI / `cmocka_driver_i2c_spi` | NOT TESTED | 需要 BMI160 和对应 I2C 或 SPI 驱动配置 |
| 1.3.10 | UART / `cmocka_driver_uart` | NOT TESTED | NSH 控制台可用只证明基础 UART；官方用例还要求独立串口收发测试 |
| 1.3.11 | UART 文件传输 | NOT TESTED | 尚未留存文件发送和接收均成功的证据 |
| 1.3.12 | RTC / `cmocka_driver_rtc` | NOT TESTED | 当前基线配置未启用 RTC 驱动 |
| 1.3.13 | Timer / `cmocka_driver_oneshot` | NOT TESTED | `ostest` 的 POSIX timer 子测试不能替代该驱动测试；需确认 `/dev/oneshot` 或 `/dev/timer` |
| 1.3.14 | 24 小时时间一致性 | NOT TESTED | 需断开 NTP，每 6 小时记录一次，共 24 小时，误差不超过 2 秒 |
| 1.3.15 | Watchdog / `cmocka_driver_watchdog -r 0..3` | NOT TESTED | `ostest` 的软件 wdog 子测试不能替代四个硬件 watchdog 场景 |
| 1.3.16 | RNG / `nist_sts 400000` | NOT TESTED | 已有 TRNG/`/dev/random` 能力，但尚未运行 NIST STS 并保存报告 |
| 1.3.17 | Crypto | NOT TESTED | 已启用 mbedTLS，但尚未按实际硬件算法执行官方 crypto 测试应用 |

## 性能与稳定性（3 项）

| 编号 | 官方用例 | 状态 | 当前证据或缺口 |
| --- | --- | --- | --- |
| 2.1.3 | Cold boot 启动时间 | NOT TESTED | 需上下电 10 次并计算平均值，要求不超过 4 秒 |
| 2.1.4 | Reboot 启动时间 | NOT TESTED | 需执行 `reboot` 10 次并计算平均值，要求不超过 6 秒 |
| 3.1.1 | 12 小时待机稳定性 | NOT TESTED | 需启用 KASAN 和 show_info，未配网静置 12 小时并保存完整串口日志 |

## BK7258 适用的品类选测项

品类自测按产品能力选测，官方文档条目很多，不计入上面的 35 项通用自测。结合本作品当前代码，建议覆盖以下类别：

| 能力 | 当前观察 | 官方品类测试结论 | 后续重点 |
| --- | --- | --- | --- |
| 2.4 GHz Wi-Fi STA | 已观察到关联、CCMP 握手、DHCP 地址和 NTP 启动 | 尚无单项 PASS | 连接/断开、扫描、WAPI show/sense、ping、TCP/UDP `iperf` |
| NetApp | 网络栈、DNS、TCP/TLS 相关代码已接入 | 尚无单项 PASS | `curl` 网页访问和 HTTP 文件下载 |
| 文件系统 | `/proc` 和手动 `/tmp` tmpfs 可用 | 尚无品类用例 PASS | 基本功能、循环创建删除、读写速度、压力和掉电场景 |
| GPIO | GPIO40/41 LED 状态反馈已接入 | 尚未完成官方 GPIO 回环 | 先完成通用 1.3.6，再补按键/PWM 等板载能力 |
| Audio | 模拟 PCM 诊断链路已接入 | 尚未完成标准 Audio 用例 | audio upper-half、录音、播放、回环 |
| BLE | 尚未完成标准 BLE 能力 | NOT TESTED | 广播、扫描、配对及 Wi-Fi 共存 |
| LCD/Camera | 当前仍待标准驱动适配 | NOT TESTED | framebuffer/LCD、H.264/H.265、摄像头链路；不适用时在报告中写明 |

Wi-Fi 启动日志只能证明基础链路工作。没有严格执行某个官方条目的步骤并保存预期结果前，不把它计为该条目 PASS。

## 下一轮执行顺序

1. 先跑无需额外硬件的 `helloxx`、`popen`、`pipe`、`cxxtest`，同时修复 `getprime`。
2. 补齐 `cmocka_mm_test`、`cmocka_sched_test`、`cmocka_syscall_test` 的构建与真机结果。
3. 利用已可用的 `/tmp` 跑 `fstest` 和 `ramtest`，再补 `md5_test` 测试文件。
4. 保存一次完整 cold boot 和一次 `reboot` 日志，然后各做 10 次启动时间统计。
5. 注册标准 GPIO、UART、Timer、RTC、Watchdog、block 设备后按通用驱动用例验收。
6. 最后执行 24 小时时间一致性、12 小时稳定性，以及 Wi-Fi/NetApp 品类测试。
