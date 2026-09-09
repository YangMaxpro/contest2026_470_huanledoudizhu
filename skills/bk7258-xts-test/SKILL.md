---
name: bk7258-xts-test
description: Run and document openvela XTS and NSH validation on a BK7258 board over UART, including ostest, mm, scanftest, boot checks, and evidence capture.
---

# BK7258 XTS 测试

在 BK7258 真机上执行 openvela XTS/NSH 测试并生成可复核证据。适用于 `ostest`、`mm`、`scanftest`、`XTS测试`、`BK7258串口测试`、`真机验证` 和测试报告整理。

## 流程

1. 确认串口设备、波特率和固件版本；串口被 miniterm、screen 或其他进程占用时，先结束占用并记录原因。
2. 发送 `help`，只运行当前固件实际提供的命令。文档中要求重新编译的命令不能当作已编译功能。
3. 需要文件写入的测试先确认挂载点。`scanftest` 使用 `/tmp/scanftest.txt`；若 `/tmp` 不可写，执行 `mount -t tmpfs tmpfs /tmp` 后再运行。
4. 一次运行一个测试，等待 `nsh>` 提示符或明确的完成标志。长时间无响应时保存已有日志，停止继续发送命令，并要求硬件 RESET 恢复设备。
5. 将原始串口输出保存到 `evidence/xts/<date>/`，文件名包含命令和结果，不只记录摘要。

## 通过标准

- `ostest`：出现 `ostest_main: Exiting with status 0`。
- `mm`：出现 `TEST COMPLETE`。
- `scanftest`：出现 `Scanf tests done... OK: 164, FAILED: 0`；若 `/tmp` 不可写，记录为环境前置条件失败。
- `hello`：出现 `Hello, World!!`。
- `getprime`：必须出现最终耗时或完成输出；只看到线程启动不能判定通过。
- `free`、`df -h`：保存输出，作为资源占用证据，不把它们当作 PASS/FAIL 测试。

## 输出规范

报告每项写明：固件文件或 SHA256、硬件型号、串口参数、执行命令、开始时间、原始日志路径、结果、失败原因和额外硬件要求。临时 tmpfs 挂载或诊断固件要明确标注为临时条件，不能写成永久修复。

## 相关文档

- `docs/xts-test-evidence.md`：本项目已完成的真机证据与复测命令。
- `SUBMISSION_CHECKLIST.md`：新硬件适配赛道提交检查表。
