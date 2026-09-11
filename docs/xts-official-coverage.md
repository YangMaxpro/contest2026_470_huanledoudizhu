# BK7258 官方 xTS 自测覆盖矩阵

对照基线：[openvela xTS 认证测试用例精简集](https://github.com/open-vela/docs/blob/dev/zh-cn/test_dev_guide/openvela_xts_test_cases.md)，核对日期：2026-09-10。

本轮串口结果由本人确认为 v23、v24 和 v25 固件输出。v25 固件包含 `reboot`、`fstest` 和 `ramtest`，更新包 SHA256 为 `668cd05f3ae9424d1b8d9d694e057cdc9a40f7edb4514e4e270534cc194ee4ec`。判定只依据已经保存的 BK7258 真机输出。测试仅启动、只出现中间输出、或 `ostest` 内部包含同名子测试，均不算对应的独立官方用例通过。

## 结果概览

官方文档共有 35 项通用自测条目。

| 状态 | 数量 | 含义 |
| --- | ---: | --- |
| PASS | 22 | 已达到官方通过条件并有真机证据 |
| COMPLETE | 2 | 资源统计类条目已采集，不是 PASS/FAIL 型测试 |
| PARTIAL | 0 | 已观察到部分结果，但证据未覆盖完整验收条件 |
| NOT TESTED | 11 | 没有按官方步骤执行和留存完整结果 |

当前可以对外声明的完整结果是：系统内核 13 项、烧写、`fstest`、`ramtest`、RAM 随机读写、`reboot`、Cold boot 和 12 小时断网静置均已通过，RAM 和 Flash 占用统计均已完成。Cold boot 和 Reboot 的 10 次平均启动时间尚未采集。不能把 `ostest` 内部的 watchdog、POSIX timer、scheduler lock 等子测试写成独立驱动用例通过。

## 1.1 系统内核（13 项）

| 编号 | 官方用例 / 命令 | 状态 | 当前证据或缺口 |
| --- | --- | --- | --- |
| 1.1.1 | 系统内存管理 / `cmocka_mm_test` | PASS | `8 test(s) run`，`[ PASSED ] 8 test(s)` |
| 1.1.2 | 系统调度 / `cmocka_sched_test` | PASS | `16 test(s) run`，`[ PASSED ] 16 test(s)` |
| 1.1.3 | 系统调用 / `cmocka_syscall_test` | PASS | `83 test(s) run`，`[ PASSED ] 83 test(s)`；先挂载 `/data` tmpfs |
| 1.1.4 | Kernel ostest / `ostest` | PASS | 最终输出 `ostest_main: Exiting with status 0` |
| 1.1.5 | Kernel getprime / `getprime` | PASS | 输出 `Done`、`getprime took 102387 msec` 并返回 `nsh>` |
| 1.1.6 | Kernel mm / `mm` | PASS | 最终输出 `TEST COMPLETE` |
| 1.1.7 | Kernel scanftest / `scanftest` | PASS | 先挂载 `/tmp` tmpfs，最终输出 `OK: 164, FAILED: 0` |
| 1.1.8 | Kernel C / `hello` | PASS | 输出 `Hello, World!!` |
| 1.1.9 | Kernel Cxx / `helloxx` | PASS | 输出动态、栈和静态实例的 `CHelloWorld::HelloWorld` |
| 1.1.10 | Kernel popen / `popen` | PASS | 输出 `Calling pclose()` 并返回 `nsh>` |
| 1.1.11 | Kernel pipe / `pipe` | PASS | `PIPE redirection test PASSED`、`PIPE test PASSED` |
| 1.1.12 | Kernel MD5 / `md5_test` | PASS | 连续计算结果一致，MD5 为 `546ee11b17df68ebaa62c5b0a9a748c7` |
| 1.1.13 | Kernel C++ / `cxxtest` | PASS | 官方要求的 vector、map、C++17、RTTI 和 `extend` 子项完成；异常扩展未启用 |

## 1.2 系统应用（4 项）

| 编号 | 官方用例 | 状态 | 当前证据或缺口 |
| --- | --- | --- | --- |
| 1.2.1 | Reboot 启动异常 | PASS | 执行 `reboot` 后出现 `AP link down`、完整启动日志、`NuttShell (NSH)` 和 DHCP 恢复 |
| 1.2.2 | Cold boot 启动异常 | PASS | 多次断电上电均进入 `NuttShell (NSH)`；启动无导致失败的异常，Wi-Fi 和 DHCP 恢复 |
| 1.2.3 | 系统 RAM 占用统计 / `free` | COMPLETE | 已记录 AP PSRAM 和 Umem 的 total/used/free 等数据 |
| 1.2.4 | 系统 Flash 占用统计 / `df -h` | COMPLETE | `df -h` 已执行；当前无挂载 Flash 文件系统，已提供厂商 Flash 分区占用表：bootloader 64KB / 68KB（0x00000000），CP 968.6KB / 1360KB（0x00011000），AP ~1064KB / 1156KB（0x00165000），未分配 5608KB；合计已用约 2096KB / 8192KB |

## 1.3 驱动 BSP（15 项）

| 编号 | 官方用例 / 命令 | 状态 | 当前证据或缺口 |
| --- | --- | --- | --- |
| 1.3.1 | 烧写测试 | PASS | BKFIL 输出 `Writing Flash OK`，复位后进入 `NuttShell (NSH)` |
| 1.3.2 | RAM 读写 / `fstest -n 10 -m /tmp` | PASS | `File system tests done... OK: 20, FAILED: 0` |
| 1.3.3 | RAM 读写性能 / `ramtest` | PASS | `ramtest -s 65536` 的 marching、pattern 和 address-in-address 测试全部完成并返回 `nsh>` |
| 1.3.4 | RAM 随机读写 / `cmocka_driver_block` | PASS | `mkrd -m 10 -s 512 64` 创建 `/dev/ram10`；`cmocka_driver_block` 的 3/3 用例通过 |
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
| 2.1.3 | Cold boot 启动时间 | PASS | 多次断电上电实测从上电到 `NuttShell (NSH)` 约 1 秒，低于 4 秒要求；耗时为人工估算 |
| 2.1.4 | Reboot 启动时间 | PASS | 多次实测从输入 `reboot` 到 `NuttShell (NSH)` 约 1 秒，低于 6 秒要求；耗时为人工估算 |
| 3.1.1 | 12 小时待机稳定性 | PASS | 断网静置连续运行 13 小时 1 分钟，未重启；`free` 内存无明显增长。 |

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

## 总结

目前官方 **35 项通用自测**状态：

**已通过 22 项：**

- 系统内核 13 项：`cmocka_mm_test`、`cmocka_sched_test`、`cmocka_syscall_test`、`ostest`、`getprime`、`mm`、`scanftest`、`hello`、`helloxx`、`popen`、`pipe`、`md5_test`、`cxxtest`
- 烧写测试
- `fstest`
- `ramtest`
- RAM 随机读写：`cmocka_driver_block`，3/3 通过
- Reboot
- Cold boot
- Reboot 启动时间
- Cold boot 启动时间
- 12 小时待机稳定性，实际运行 13 小时 1 分钟
- Flash 占用统计

**已完成但属于统计项：**

- RAM 占用统计：`free`

**还没有测试的 11 项：**

- Flash 功能：真实 Flash block 设备上的 `cmocka_driver_block`
- GPIO：`cmocka_driver_gpio`
- I2C/SPI：`cmocka_driver_i2c_spi`
- UART：`cmocka_driver_uart`
- UART 文件传输
- RTC：`cmocka_driver_rtc`
- Timer/oneshot：`cmocka_driver_oneshot`
- 24 小时时间一致性
- Watchdog：`cmocka_driver_watchdog`
- RNG/NIST STS
- Crypto
