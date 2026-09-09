# BK7258 真机 XTS 测试证据

硬件：Beken BK7258 R1 开发板

串口：`/dev/ttyUSB0`，115200 8N1

关键串口原文摘录：[`evidence/xts/2026-09-09/serial-key-results.log`](../evidence/xts/2026-09-09/serial-key-results.log)

## 已完成

| 命令 | 结果 | 证据关键字 |
| --- | --- | --- |
| `ostest` | PASS | `ostest_main: Exiting with status 0` |
| `mm` | PASS | `TEST COMPLETE` |
| `scanftest` | PASS（挂载 tmpfs 后） | `Scanf tests done... OK: 164, FAILED: 0` |
| `hello` | PASS | `Hello, World!!` |
| `free` | 已采集 | AP PSRAM 与 Umem 使用统计 |
| `df -h` | 已采集 | `/proc` procfs 挂载信息 |

## scanftest 前置条件

当前镜像启动时只有 `/proc` procfs，`/tmp` 不可写。执行以下命令后测试通过：

```sh
mount -t tmpfs tmpfs /tmp
scanftest
```

结果：

```text
Back to Back Test...
Test PASSED.
Scanf tests done... OK: 164, FAILED: 0
```

该挂载是运行时临时状态，重启后需要重新挂载。若要做到开机自动满足条件，应在启动脚本或配置中加入 `/tmp` 的 tmpfs 挂载并重新构建固件。

## 未完成或需要单独处理

- `getprime` 在当前镜像只打印线程启动信息，未返回最终耗时；不能判定通过，需要单独排查或重新编译验证。
- `cmocka_mm_test`、`cmocka_sched_test`、`cmocka_syscall_test` 未出现在当前镜像的 `help` 列表，需要打开对应配置后重新构建。
- GPIO、SPI/I2C、RTC、UART 回环、BLE 和 Wi-Fi 性能用例需要对应外设、手机或第二台 PC，不能仅凭当前串口完成。

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
