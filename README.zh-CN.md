# ccs

[English](README.md) | 中文

`ccs` 是一个轻量的 Code CLI Suite，用于快速启动 Claude Code、Codex、OpenCode，并提供原生参数透传、快速模型切换、统一启动模式和项目共享记忆。

它不接管原工具 UI，也不二次显示原工具界面。`ccs` 只做这些事：

- 保留各工具原始命令行参数
- 设置 app 默认模型或全局默认模型
- 使用一次性模型覆盖
- 映射 `--cc-auto`、`--cc-danger`、`--cc-plan` 快速模式
- 通过 `.ccs/memory.md` 共享项目记忆

## 快速开始

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

原工具自己的辅助命令会直接透传，不注入模型和记忆：

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

模型优先级：

```text
原生 app 模型参数 > --cc-model > app 默认模型 > 全局默认模型 > 原工具自身默认
```

如果同一次命令同时写 `--cc-model` 和原生 `--model` / `-m`，`ccs` 会报冲突错误。

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

模式映射：

| 模式 | Claude | Codex | OpenCode |
| --- | --- | --- | --- |
| `--cc-auto` | `--permission-mode auto` | `--ask-for-approval never` | `--auto` |
| `--cc-danger` | `--dangerously-skip-permissions` | `--dangerously-bypass-approvals-and-sandbox` | `--auto` 并提示 |
| `--cc-plan` | `--permission-mode plan` | 不支持 | 不支持 |

## 共享记忆

`ccs` 使用 `.ccs/memory.md` 作为不同 code CLI 之间的项目共享记忆。

```bash
ccs memory init
ccs memory note "Codex 额度用完，后续用 Claude Code 继续。"
ccs memory task "继续实现 defaults.py。"
ccs memory decision "TUI 路线不进入主接口。"
ccs memory show
ccs memory status
ccs memory path
```

`ccs <app>` 默认会注入一段记忆读取提示。关闭本次记忆注入：

```bash
ccs claude --cc-no-memory
```

`.ccs/memory.local.md` 默认忽略，也默认不注入。

## 模型和 Provider

```bash
ccs providers
ccs models
ccs models openrouter
ccs model show ds/flash
ccs models add or/qwen3-coder qwen/qwen3-coder
ccs models rm or/qwen3-coder
```

`ccs` 不保存 API key。Provider 命令只显示对应环境变量是否存在，不打印密钥内容。

## 开发

测试文件放在 `tests/` 下：

```bash
python -m unittest discover -s tests
python -m compileall ccs
```

历史代码、实验原型和旧 README 统一放在 `docs/backup/`。

## 不做什么

- 不提供 TUI。
- 不提供 tmux session 管理。
- 不提供 daemon。
- 不迁移私有 session。
- 不保存 API key。

