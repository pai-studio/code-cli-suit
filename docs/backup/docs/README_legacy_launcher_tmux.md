# ccs

`ccs` 是一个极低负担的代码工具启动器：用 `provider/model` 选择模型，然后启动原始工具 UI。

当前稳定主路径只有两条：

- 轻量 launcher：`ccs claude --cc-model ds/flash`
- 可选 tmux session：`ccs tmux claude --cc-name code --cc-model ds/flash`

`ccs` 不保存 API key，不接管 Claude Code 的交互界面，不默认打开 panel。

## Quick Start

```bash
# 安装
pip install -e . --no-build-isolation

# 查看 provider 和模型
ccs providers
ccs models

# 轻量启动原始 Claude Code UI
ccs claude --cc-model ds/flash

# Claude 原始参数照常写在后面
ccs claude --cc-model an/sonnet --permission-mode acceptEdits

# 原始 Claude help 也照常可用
ccs claude --help
```

## 推荐心智模型

`ccs claude ...` 应该被理解成“带模型注入能力的 `claude ...`”。

规则只有一个：`ccs` 只解析 `--cc-*` 参数，其余参数全部原样传给 Claude。

```bash
ccs claude --cc-model ds/flash --permission-mode acceptEdits
```

这里：

- `--cc-model ds/flash` 属于 `ccs`
- `--permission-mode acceptEdits` 属于 Claude

当指定 `--cc-model` 时，`ccs` 会为本次启动生成隔离的 Claude 配置，然后直接执行原始 `claude`。它不会进入 tmux，不会创建后台 daemon session，也不会打开 UI panel。

未指定任何 `--cc-*` 参数时，`ccs claude ...` 直接透传：

```bash
ccs claude --help
ccs claude auth
ccs claude doctor
```

## 多窗口还是 tmux

如果你的目标只是同时开两个 Claude Code，例如一个写代码、一个 review，最简单的方案是开两个终端窗口：

```bash
# terminal 1
ccs claude --cc-name code --cc-model ds/flash

# terminal 2
ccs claude --cc-name review --cc-model an/sonnet
```

这是默认推荐路径。它最接近原始 Claude Code，界面最干净，出问题的组件最少。

tmux 的意义是可选的 session 管理能力：

- 终端关闭后 session 仍可继续运行
- 可以按名字重新 attach
- 适合远程机器、长任务、临时断线
- 可以统一 list/kill/switch 命名 session

如果你不需要这些能力，不需要使用 tmux。

## tmux Session

tmux 路线必须显式写 `ccs tmux ...`，避免和轻量 launcher 混用。

```bash
ccs tmux claude --cc-name code --cc-model ds/flash
ccs tmux claude --cc-name review --cc-model an/sonnet

ccs tmux attach code
ccs tmux attach review
```

常用管理命令：

```bash
ccs tmux list
ccs tmux attach <name>
ccs tmux switch <name> [model]
ccs tmux kill <name>
ccs tmux monitor <name> --lines 80
ccs tui
```

`ccs tmux attach <name>` 会为每个会话使用独立 view session，避免两个终端 attach 到同一个 tmux session 后同步当前窗口和输入。

tmux 默认不启用 mouse，因为 mouse 会干扰 Claude Code 的焦点。如果你明确需要鼠标滚动：

```bash
export CCS_TMUX_MOUSE=1
```

如果老用户想显示 tmux 侧边状态栏：

```bash
export CCS_TMUX_SIDEBAR=1
```

## 模型写法

统一使用 `provider/model`：

```text
an/sonnet
an/opus
ds/flash
ds/pro
or/kimi-k2.6
or/glm-5
or/gemini-2.5-flash
mm/m2.7
openai/gpt-5
```

Provider 可以用简称：

| 简称 | Provider | API key |
| --- | --- | --- |
| `an` | `anthropic` | `ANTHROPIC_API_KEY` |
| `ds` | `deepseek` | `DEEPSEEK_API_KEY` |
| `or` | `openrouter` | `OPENROUTER_API_KEY` |
| `mm` | `minimax` | `MINIMAX_API_KEY` |
| `openai` | `openai` | `OPENAI_API_KEY` |

OpenRouter 也保持严格两段式：

```text
or/kimi-k2.6 -> moonshotai/kimi-k2.6
```

添加自己的 OpenRouter 映射：

```bash
ccs models add or/qwen3-coder qwen/qwen3-coder
ccs model show or/qwen3-coder
```

## API Key

`ccs` 不管理密钥，也不提供 `store-key`。请使用环境变量：

```bash
export DEEPSEEK_API_KEY="sk-xxx"
export OPENROUTER_API_KEY="sk-or-v1-xxx"
export MINIMAX_API_KEY="sk-xxx"
export ANTHROPIC_API_KEY="sk-ant-xxx"
```

`ccs providers` 只显示 `set` / `missing`，不会打印密钥内容。

## ccs 参数

| 参数 | 说明 |
| --- | --- |
| `--cc-model <model>` | 指定 `provider/model` |
| `--cc-name <name>` | 指定隔离配置或 tmux session 名；不填会自动生成 |
| `--cc-project <dir>` | 指定项目目录，默认当前目录 |
| `--cc-dry-run` | 打印将执行的命令，不真正启动 |
| `--cc-no-attach` | 仅用于 `ccs tmux claude` |

## 常用命令

```bash
ccs --help
ccs --help-zh

ccs providers
ccs models
ccs models or
ccs model show ds/flash

ccs claude --cc-model ds/flash
ccs claude --cc-model an/sonnet --permission-mode acceptEdits
ccs claude --cc-model or/kimi-k2.6 --cc-project ~/work/app
ccs claude --cc-model ds/flash --cc-dry-run

ccs tmux claude --cc-name code --cc-model ds/flash
ccs tmux attach code
ccs tmux list
```

## claude-switch 兼容命令

旧命令仍保留：

```bash
claude-switch list
claude-switch deepseek-pro
claude-switch deepseek-flash
claude-switch openrouter/kimi-k2.6
```

`ccs --cc-model` 也兼容旧名称：

```bash
ccs claude --cc-model deepseek-flash
ccs claude --cc-model openrouter/kimi-k2.6
```

## Troubleshooting

### `ccs: claude not found`

安装 Claude Code，并确认：

```bash
claude --help
```

### `tmux not found`

只有 `ccs tmux ...` 需要 tmux：

```bash
brew install tmux
```

### `unknown model spec '<name>'`

查看可用模型：

```bash
ccs models
```

然后使用 `provider/model`：

```bash
ccs claude --cc-model ds/flash
```
