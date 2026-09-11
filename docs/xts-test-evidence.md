# BK7258 真机 XTS 测试证据

硬件：Beken BK7258 R1 开发板  
串口：`/dev/ttyUSB0`，115200 8N1  
固件口径：v23–v25；v25 包含 `reboot`、`fstest`、`ramtest`，最新更新包 SHA256：`668cd05f3ae9424d1b8d9d694e057cdc9a40f7edb4514e4e270534cc194ee4ec`

关键串口汇总摘录：[`evidence/xts/2026-09-09/serial-key-results.log`](../evidence/xts/2026-09-09/serial-key-results.log)。完整逐项对照见 [`xts-official-coverage.md`](xts-official-coverage.md)。

## 原始串口日志

下列文件从 Ubuntu 测试机 `/home/yang/` 原样复制，并按文件实际保存日期归档：

| 日期 | 原始日志 |
| --- | --- |
| 2026-09-09 | `xts-kernel-v20-serial.log`、`xts-kernel-v21-serial.log`、`xts-kernel-v22-serial.log`、`xts-kernel-v23-serial.log` |
| 2026-09-10 | `xts-kernel-v24-serial.log`、`xts-kernel-v25-serial.log` |
| 2026-09-11 | `xts-coldboot-v25-serial.log` |

`serial-key-results.log` 是便于评审快速核对的汇总摘录，不替代上述原始日志。公开前已检查常见密码、PSK、API Key、Authorization、Bearer Token 字段，未发现匹配项。

## 早期构建与主机测试日志

`evidence/build-and-host-tests/` 保存 XTS 串口测试前的真实项目日志：

| 日期 | 文件数 | 内容 |
| --- | ---: | --- |
| 2026-09-05 | 3 | BK7258 打包烧录与自动烧录日志 |
| 2026-09-07 | 36 | v19-v25、PCM、语音、HTTPS、Wi-Fi profile 的构建与主机测试日志 |
| 2026-09-08 | 8 | 时间、voice v35/v36 和 RTSA 基线构建/测试日志 |

2026-09-06 没有找到可归属于本项目的构建、烧录或串口日志，因此不创建空记录。以上日志用于说明开发和验证过程，不计作官方 XTS 真机用例通过证据。

## 已完成

| 命令 | 结果 | 关键输出 |
| --- | --- | --- |
| `ostest` | PASS | `ostest_main: Exiting with status 0` |
| `cmocka_mm_test` | PASS | `8 test(s) run`，`[ PASSED ] 8 test(s)` |
| `cmocka_sched_test` | PASS | `16 test(s) run`，`[ PASSED ] 16 test(s)` |
| `cmocka_syscall_test` | PASS | `83 test(s) run`，`[ PASSED ] 83 test(s)`；先挂载 `/data` tmpfs |
| `getprime` | PASS | `Done`、`getprime took 102387 msec`，返回 `nsh>` |
| `mm` | PASS | `TEST COMPLETE` |
| `scanftest` | PASS（挂载 tmpfs 后） | `Scanf tests done... OK: 164, FAILED: 0` |
| `hello` | PASS | `Hello, World!!` |
| `helloxx` | PASS | 动态、栈和静态实例均输出 `CHelloWorld::HelloWorld` |
| `popen` | PASS | 输出 `Calling pclose()` 并返回 `nsh>` |
| `pipe` | PASS | `PIPE redirection test PASSED`、`PIPE test PASSED` |
| `md5_test` | PASS | 连续计算结果一致 |
| `cxxtest` | PASS | vector、map、C++17、RTTI 和 `extend` 子项完成 |
| `reboot` | PASS | 复位后恢复 `NuttShell (NSH)`，Wi-Fi/DHCP 恢复 |
| Cold boot | PASS | 多次断电上电后进入 `NuttShell (NSH)` |
| `fstest` | PASS | `File system tests done... OK: 20, FAILED: 0` |
| `ramtest` | PASS | marching、pattern、address-in-address 测试完成并返回 `nsh>` |
| `cmocka_driver_block`（RAM） | PASS | `/dev/ram10` 创建成功，3/3 用例通过 |
| 12 小时断网静置 | PASS | 连续运行约 13 小时，未重启，内存无明显增长 |
| `free` | 已采集 | 保存 AP PSRAM 与 Umem 的 total/used/free 等数据 |
| `df -h` | 已采集 | 保存当前挂载文件系统；Flash 分区占用见覆盖矩阵 |

## scanftest 前置条件

当前镜像启动时 `/tmp` 可能不可写，先执行：

```sh
mount -t tmpfs tmpfs /tmp
scanftest
```

`/data` 用于 `cmocka_syscall_test` 时同样需要先挂载 tmpfs。以上挂载是运行时临时状态，重启后需要重新执行；若要开机自动挂载，应修改启动脚本或配置后重新构建固件。

## 尚未完成的通用条目

以下项目在覆盖矩阵中保持 `NOT TESTED`：真实 Flash block、GPIO 回环、I2C/SPI、独立 UART 收发、UART 文件传输、RTC、oneshot/timer、24 小时时间一致性、硬件 watchdog、NIST STS RNG、Crypto。它们需要对应驱动、外设、第二台设备或长时间观察，不能用相近功能的日志替代。

## 复测记录模板

```text
日期：
固件文件/SHA256：
设备：BK7258 R1
串口：/dev/ttyUSB0 115200 8N1
命令：
结果：PASS / FAIL / BLOCKED
关键输出：
原始日志：
```
