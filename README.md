# ccs

`ccs` 是 Code CLI Suite：面向 Claude Code、Codex、OpenCode 等 code CLI 的快速启动工具。

它不接管原工具 UI，不做 TUI、tmux session 或 daemon。`ccs` 只做四件事：

- 保留原工具参数使用方式
- 统一一次性模型覆盖和默认模型
- 提供 `--cc-auto`、`--cc-danger`、`--cc-plan` 快速模式
- 通过 `.ccs/memory.md` 共享项目记忆

## Quick Start

```bash
pip install -e . --no-build-isolation

ccs memory init
ccs use claude ds/flash
ccs claude
```

## 启动 App

```bash
ccs claude
ccs codex
ccs opencode
```

app 后面的非 `--cc-*` 参数全部原样传给原工具：

```bash
ccs claude --permission-mode plan
ccs codex --sandbox workspace-write "fix tests"
ccs opencode run "review this repo"
```

纯原生命令会直接透传，不注入模型和记忆：

```bash
ccs claude --help
ccs claude doctor
ccs codex --help
```

## 模型

一次性覆盖模型：

```bash
ccs claude --cc-model an/sonnet
ccs codex --cc-model openai/gpt-5
ccs opencode --cc-model or/kimi-k2.6
```

设置默认模型：

```bash
ccs use claude ds/flash
ccs use codex openai/gpt-5
ccs use opencode or/kimi-k2.6
ccs use ds/flash
ccs current
```

覆盖顺序：

```text
原生 app 模型参数 > --cc-model > app 默认模型 > 全局默认模型 > 原工具自身默认
```

如果同一次命令同时写 `--cc-model` 和原生 `--model` / `-m`，`ccs` 会报错。

## 快速模式

```bash
ccs claude --cc-auto
ccs codex --cc-auto
ccs opencode --cc-auto

ccs claude --cc-danger
ccs codex --cc-danger
ccs opencode --cc-danger

ccs claude --cc-plan
```

映射规则：

| 模式 | Claude | Codex | OpenCode |
| --- | --- | --- | --- |
| `--cc-auto` | `--permission-mode auto` | `--ask-for-approval never` | `--auto` |
| `--cc-danger` | `--dangerously-skip-permissions` | `--dangerously-bypass-approvals-and-sandbox` | `--auto` 并提示 |
| `--cc-plan` | `--permission-mode plan` | 不支持 | 不支持 |

## 共享记忆

`ccs` 默认使用项目内的 `.ccs/memory.md` 作为跨 CLI 共享记忆。

```bash
ccs memory init
ccs memory note "Codex 额度用完，后续用 Claude Code 继续。"
ccs memory task "继续实现 defaults.py。"
ccs memory decision "TUI 路线不进入主接口。"
ccs memory show
ccs memory status
ccs memory path
```

`ccs <app>` 默认会注入记忆读取提示。关闭本次记忆注入：

```bash
ccs claude --cc-no-memory
```

`.ccs/memory.local.md` 默认不提交，也默认不注入。

## 模型和 Provider

```bash
ccs providers
ccs models
ccs models openrouter
ccs model show ds/flash
ccs models add or/qwen3-coder qwen/qwen3-coder
ccs models rm or/qwen3-coder
```

`ccs` 不保存 API key。Provider 只显示环境变量是否存在，不打印密钥内容。

## 开发与测试

测试文件放在 `tests/` 下：

```bash
python -m unittest discover -s tests
python -m compileall ccs
```

历史代码、实验原型和旧 README 统一放在 `docs/backup/`。

## 不做什么

- 不注册 `claude-switch`
- 不提供 `ccs tui`
- 不提供 `ccs tmux`
- 不提供 `ccs daemon`
- 不管理私有 session
- 不承诺不同 CLI 的私有 session 无损迁移

旧代码已经归档到 `docs/backup/`。
