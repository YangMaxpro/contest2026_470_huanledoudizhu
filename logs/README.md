# logs/ - AI Coding 日志目录

存放开发过程中与 AI 工具的对话日志，和作品代码一并提交。

> 本目录已包含本项目实际导出的 Claude Code 和 Codex JSONL 会话日志，不是占位示例。

当前包含 1 个 2026-08-31 Claude Code 会话和 6 个 2026-09-08 开始的 Codex Desktop 会话。最长的 Codex 会话持续到 2026-09-11；目录日期按官方规则使用会话开始日期，因此不另外拆分成 09-09、09-10 和 09-11 的假会话。

## 目录结构

```text
logs/
└── <github_login>/              # GitHub 用户名，一人一目录
    ├── manifest.json            # 会话清单
    └── <date>/                  # 日期 YYYY-MM-DD
        └── <tool>__<sid>.jsonl  # 一个会话一个文件
```

- `<tool>`：`claude-code` / `opencode` / `codex` / `kiro`
- 每个 `.jsonl` 每行一个事件，由组委会提供的日志归集工具导出，只提交 JSONL 本身。

导出与提交步骤、字段定义见[《AI Coding 日志归集与提交手册》](https://github.com/open-vela/docs/blob/dev-ai-contest-2026/zh-cn/contest_2026/ai_coding_log_guide.md)。
