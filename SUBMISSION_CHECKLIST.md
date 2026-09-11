# 新硬件适配赛道提交检查表

仓库：`contest2026_470_huanledoudizhu`

## 代码

- [x] 完整源码已通过 PR #2 合入官方作品仓的 `dev-ai-contest-2026` 分支。
- [x] 提交源码、配置、板级文件和文档；`.bin` 只作为辅助产物，不能替代源码。
- [x] `openvela.xml` 固定到 BK7258 NuttX 提交 `ebd2bba1677d695586860ee7050f987b60bdfe06`。
- [x] `board/contest_board/`、`app/xiaopai/` 和 `tools/` 的修改均有说明。

## 当前仓库状态（2026-09-09 核查）

- 官方作品仓 PR #2 已合入 `dev-ai-contest-2026`，合并提交为 `2cce7a0`。
- 官方作品仓 PR #4 已合入 `dev-ai-contest-2026`，将 NuttX 固定提交更新为 `ebd2bba1677d695586860ee7050f987b60bdfe06`。
- 个人 fork 的 `dev-ai-contest-2026` 已于 2026-09-09 更新为完整提交 `85fccfe`，包含源码、证据和 AI Coding 材料。
- NuttX fork 的 `feat/bk7258-chip` 已整理为单提交 `ebd2bba1677d`，包含当前真机使用的 BK7258 芯片级实现及最终格式修正。
- 官方作品仓 PR：<https://github.com/open-vela/contest2026_470_huanledoudizhu/pull/2>（已合入）。
- `open-vela/nuttx` PR #360 仍为 Open，现为 1 commit / 44 files，全部位于 `arch/arm/src/bk7258/`。checkpatch 和 CLA 已通过，其余 CI 执行中，等待 code owner review。

## 新硬件适配说明

- 芯片：Beken BK7258，双核 Cortex-M33F。
- 板级适配：启动入口、向量表、UART0、SysTick/NVIC、堆内存、Flash 链接脚本。
- 应用适配：小派控制层、NSH 命令、LED 状态反馈和能力探测。
- 验证方式：编译产物、烧录命令、串口参数、真机日志和已知限制。

## AI Coding 材料

- [x] `logs/YangMaxpro/manifest.json` 已记录真实会话。
- [x] `logs/YangMaxpro/2026-08-31/claude-code__e06d80c6-72d7-44cb-88f7-c65861b19c4d.jsonl` 是实际 JSONL 日志，不是 example 占位。
- [x] `logs/YangMaxpro/2026-09-08/` 已补导 6 个与本项目有关的 Codex Desktop 会话，共 6230 条事件；同一会话持续到 2026-09-11，按官方规则归入会话开始日期。
- [x] 全部 7 份 AI Coding 日志已通过赛事 `validate-log.py` 校验（8400 条事件，`ALL OK`）。
- [x] `skills/bk7258-xts-test/SKILL.md` 已沉淀 BK7258 XTS 测试流程。
- [x] `skills/bk7258-openvela-development/SKILL.md` 已沉淀 BK7258 芯片、板级、构建、镜像和真机开发流程。

## 报告与演示

- [x] README 已填写队伍名称、成员分工、选题方向和仓库链接。

- [x] README 和适配报告已区分已完成、待适配和需要额外硬件的能力。

- [x] `evidence/xts/2026-09-09/serial-key-results.log` 已保留 `ostest_main: Exiting with status 0`、`TEST COMPLETE` 和 `OK: 164, FAILED: 0` 真机串口证据。

  
