# 新硬件适配赛道提交检查表

仓库：`contest2026_470_huanledoudizhu`

## 代码

- [x] 将当前完整源码推送到个人 fork 的 `dev-ai-contest-2026` 工作分支；待向官方仓库同名分支发起 PR。
- [x] 提交源码、配置、板级文件和文档；`.bin` 只作为辅助产物，不能替代源码。
- [x] `openvela.xml` 固定到 BK7258 NuttX 提交 `8f2eefdf575341b146b0e22c5dfb9b6fa218120c`。
- [x] `board/contest_board/`、`app/xiaopai/` 和 `tools/` 的修改均有说明。

## 当前仓库状态（2026-09-09 核查）

- 官方作品仓 `open-vela/contest2026_470_huanledoudizhu` 的默认分支正确；需从个人 fork 的 `dev-ai-contest-2026` 向其发起 PR。
- 个人 fork 的 `dev-ai-contest-2026` 已于 2026-09-09 更新为完整提交 `85fccfe`，包含源码、证据和 AI Coding 材料。
- NuttX fork 的 `feat/bk7258-chip` 已更新到 `8f2eefdf575`，包含当前真机使用的 BK7258 芯片级实现。
- 官方仓 PR 尚未创建；创建后将 PR 链接补入本清单和 README。
- `open-vela/nuttx` PR #360 仍为 Open，当前显示 30 commits / 76 files，且 CLA 检查提示 `1409614428@qq.com` 未签署。应先签署 CLA，再执行 `/check-cla`；同时把 PR 整理为仅包含 BK7258 芯片级改动，避免夹带目标分支的公共提交。

## 新硬件适配说明

- 芯片：Beken BK7258，双核 Cortex-M33F。
- 板级适配：启动入口、向量表、UART0、SysTick/NVIC、堆内存、Flash 链接脚本。
- 应用适配：小派控制层、NSH 命令、LED 状态反馈和能力探测。
- 验证方式：编译产物、烧录命令、串口参数、真机日志和已知限制。

## AI Coding 材料

- [x] `logs/YangMaxpro/manifest.json` 已记录真实会话。
- [x] `logs/YangMaxpro/2026-08-31/claude-code__e06d80c6-72d7-44cb-88f7-c65861b19c4d.jsonl` 是实际 JSONL 日志，不是 example 占位。
- [x] `skills/bk7258-xts-test/SKILL.md` 已沉淀 BK7258 XTS 测试流程。
- [ ] 若继续使用 Codex/其他工具，按组委会手册追加真实导出的 JSONL，不要手工伪造事件。

## 报告与演示

- [ ] 填写队伍名称、成员分工、选题方向和仓库链接。
- [ ] 如实区分已完成、待适配和需要额外硬件的能力。
- [ ] 附上真机照片、串口日志或录屏；日志中保留 `ostest_main: Exiting with status 0`、`TEST COMPLETE` 和 `OK: 164, FAILED: 0`。
- [ ] 演示视频在提交前完整播放一遍，并确认文件可解码。
