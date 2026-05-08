# ccs

`ccs` 用 tmux 管理多个 Claude Code 会话，并允许每个会话使用不同的 `provider/model`。

`claude-switch` 仍然保留为兼容命令；日常使用优先使用 `ccs`。

## Quick Start

```bash
# 安装
pip install -e . --no-build-isolation

# 查看 provider 和模型
ccs providers
ccs models

# 用 DeepSeek Flash 启动一个托管 Claude 会话
ccs claude --cc-model ds/flash

# 用 Sonnet 启动，并把参数原样传给 Claude
ccs claude --cc-model an/sonnet --permission-mode acceptEdits

# 查看托管会话
ccs list

# 打开 TUI 管理 session
ccs tui

# 用新模型重启已有会话
ccs switch api-review ds/pro

# 回到最近的会话
ccs attach
```

## ccs 的心智模型

`ccs claude ...` 看起来应该像原始 `claude ...`。

区别只有一个：`ccs` 只解析 `--cc-*` 参数，其余参数全部传给 Claude。

```bash
# 原始 Claude help，不创建会话
ccs claude --help

# 创建托管会话；--permission-mode 是 Claude 原始参数
ccs claude --cc-model ds/flash --permission-mode acceptEdits
```

当你指定 `--cc-model` 时，`ccs` 会：

1. 解析 `provider/model`
2. 生成当前会话专属 settings 文件
3. 为当前会话生成独立 `CLAUDE_CONFIG_DIR`
4. 用 `CLAUDE_CONFIG_DIR=<session-config> claude --settings <session-settings>` 启动 Claude
5. 把 Claude 放入 tmux session `ccs`
6. 自动 attach 到该会话

`CLAUDE_CONFIG_DIR` 隔离很重要：Claude Code 的 session history、UI 状态、credentials、plugins 默认都在 `~/.claude` 下。`ccs` 为每个托管 session 自动使用独立目录，避免同一个项目里开 `code` 和 `review` 时消息历史或输入状态互相串联。

未指定 `--cc-model` 时，`ccs claude ...` 直接透传到原始 Claude。

## 常用命令

### 启动会话

```bash
# 自动生成会话名，项目目录为当前目录
ccs claude --cc-model ds/flash

# 指定会话名
ccs claude --cc-model ds/pro --cc-name api-review

# 指定项目目录
ccs claude --cc-model or/kimi-k2.6 --cc-project ~/work/app

# 创建后不自动进入
ccs claude --cc-model an/sonnet --cc-no-attach

# 预览将执行的命令，不创建会话
ccs claude --cc-model ds/flash --cc-dry-run
```

如果 `--cc-name` 指向已有会话，`ccs` 会更新并重启该会话：

```bash
ccs claude --cc-name api-review --cc-model ds/pro
ccs claude --cc-name api-review --cc-model ds/pro --permission-mode acceptEdits
```

### 传递 Claude 原始参数

```bash
ccs claude --cc-model an/sonnet --permission-mode acceptEdits
ccs claude --cc-model ds/flash --add-dir ../shared
ccs claude --cc-model an/sonnet --dangerously-skip-permissions
```

`--permission-mode`、`--add-dir`、`--dangerously-skip-permissions` 都属于 Claude，`ccs` 不解析。

### 管理会话

```bash
# 打开交互式 session 管理界面
ccs tui

# 列出所有托管会话
ccs list

# JSON 输出，适合脚本
ccs list --json

# attach 最近的会话
ccs attach

# attach 指定会话
ccs attach api-review

# 删除会话并清理会话 settings
ccs kill api-review

# 同时监控多个 session 的最近输出，不进入 Claude
ccs monitor
ccs monitor api-review ui-fix --lines 80
```

低负担默认路线是：用 `ccs claude ...` 创建/进入会话，用 `ccs list/attach/switch/kill/monitor` 在命令行管理会话。tmux 内部只承担隔离运行，不要求用户理解 pane/window。

同一个项目可以同时开多个独立终端窗口：

```bash
ccs claude --cc-name code --cc-model ds/flash
ccs claude --cc-name review --cc-model an/sonnet --cc-no-attach

# 在另一个终端窗口进入 review
ccs attach review
```

`ccs attach <name>` 会为每个会话使用独立的 tmux view session，避免两个终端 attach 到同一个 tmux session 后互相同步当前窗口和输入。

### TUI 快捷键

```text
Enter  attach 当前 session
n      新建 Claude session，name 可空，默认模型 ds/flash
s      切换当前 session 模型
k      删除当前 session
r      刷新列表
?      查看帮助
q      退出 TUI
```

TUI 退出不会停止 tmux 中运行的 session。

进入 session 后默认保持 Claude Code 全屏，不显示额外侧栏，避免把用户带入 tmux pane/window 细节。

### 会话内快捷键

```text
F2        打开 ccs session 选择器
F3        切到上一个 session
F4        切到下一个 session
F10       离开当前附着，Claude 继续后台运行
Ctrl-b s  打开 ccs session 选择器备用方式
Ctrl-b p  切到上一个 session 备用方式
Ctrl-b n  切到下一个 session 备用方式
Ctrl-b d  detach 备用方式
```

正常情况下不需要手动恢复焦点；`ccs attach`、session 切换、picker 选择后都会自动切回 Claude 主输入 pane。

滚动：

```text
Fn+↑      向上翻页查看上下文
Fn+↓      向下翻页回到新内容
Ctrl-b [   进入滚动/copy-mode
j / k      向下 / 向上滚动一行
u / d      向上 / 向下滚动半屏，不需要 PageUp/PageDown
g / G      到历史顶部 / 底部
q / Esc    退出滚动/copy-mode
```

这些提示也会显示在 ccs tmux 状态栏里。

默认不启用 tmux mouse，因为它会拦截 Claude Code 的鼠标/焦点行为，可能导致输入框不自动获得焦点。如果你更想用鼠标滚轮，可以显式开启：

```bash
export CCS_TMUX_MOUSE=1
```

开启后重新 `ccs attach <name>` 生效。

如果老用户仍然想显示 tmux 侧边状态栏，可以显式打开：

```bash
export CCS_TMUX_SIDEBAR=1
```

默认路线基于 tmux，优先保证现有用户稳定可用，并隐藏不必要的 tmux 界面。后续会并行推进 `ccsd + workbench` 最终方案，用真正的左侧可点击 session 列表和右侧嵌入终端替代 tmux 兼容层。

### 切换或重启会话

```bash
# 切到新模型并重启
ccs switch api-review ds/pro

# 不切模型，只沿用当前模型重启
ccs switch api-review

# 切回默认配置
ccs switch api-review default

# 如果会话不存在，允许创建
ccs switch api-review ds/pro --create

# 创建时指定项目目录
ccs switch api-review ds/pro --create --cc-project ~/work/app
```

`switch` 是管理命令，不透传 Claude 原始参数。需要同时指定 Claude 参数时，使用：

```bash
ccs claude --cc-name api-review --cc-model ds/pro --permission-mode acceptEdits
```

### 模型和 provider

```bash
# 查看 provider，以及对应 API key 环境变量是否已设置
ccs providers

# 查看内置模型
ccs models

# 只看 OpenRouter 模型
ccs models or

# 查看某个模型会解析成什么
ccs model show or/kimi-k2.6

# 为 OpenRouter 添加自定义模型映射，不保存 API key
ccs models add or/qwen3-coder qwen/qwen3-coder

# 删除自定义映射
ccs models rm or/qwen3-coder
```

常用 `provider/model`：

```text
an/sonnet
an/opus
ds/flash
ds/pro
or/kimi-k2.6
or/glm-5
or/gemini-2.5-flash
mm/m2.7
```

OpenRouter 仍然保持严格两段式 `provider/model`。例如：

```text
or/kimi-k2.6 -> moonshotai/kimi-k2.6
```

如果你要用新的 OpenRouter 模型，添加本地映射即可：

```bash
ccs models add or/my-model provider-author/real-model-id
```

## ccs 参数

| 参数 | 说明 |
| --- | --- |
| `--cc-model <model>` | 使用 `provider/model` 创建托管会话 |
| `--cc-name <name>` | 指定会话名，不填则自动生成 |
| `--cc-project <dir>` | 指定项目目录，默认当前目录 |
| `--cc-no-attach` | 创建后不自动 attach |
| `--cc-dry-run` | 打印生成的命令和配置路径，不创建会话 |

## 会话隔离

`ccs` 不直接修改项目里的 `.claude/settings.json`。

每个托管会话会拥有自己的 settings 文件：

```text
~/.ccs/sessions/*.claude.settings.json
```

这些 settings 文件由 `provider/model` 生成，并以 `0600` 权限保存，因为 Claude Code 当前可能需要在 settings 中接收 provider token。

因此，同一个项目可以同时运行多个不同模型：

```bash
ccs claude --cc-model an/sonnet --cc-name impl
ccs claude --cc-model ds/flash --cc-name review
ccs claude --cc-model or/kimi-k2.6 --cc-name explore
```

## API Key

`ccs` 不保存 API key，也不提供 `store-key` 之类的密钥管理命令。请用环境变量：

```bash
export DEEPSEEK_API_KEY="sk-xxx"
export OPENROUTER_API_KEY="sk-or-v1-xxx"
export MINIMAX_API_KEY="sk-xxx"
```

`ccs providers` 只显示 `set` / `missing`，不会打印密钥内容。

## claude-switch 兼容命令

旧的 profile 仍然可用：

```bash
claude-switch list
claude-switch deepseek-pro
claude-switch deepseek-flash
claude-switch openrouter/glm-5
claude-switch openrouter/kimi-k2.6
```

`ccs --cc-model` 也继续兼容旧名称：

```bash
ccs claude --cc-model deepseek-flash
ccs claude --cc-model openrouter/kimi-k2.6
```

## claude-switch 命令

| Command | Description |
| --- | --- |
| `claude-switch` | Interactive picker |
| `claude-switch <name>` | Switch by fuzzy name |
| `claude-switch -` | Back to previous |
| `claude-switch list` | List all profiles |
| `claude-switch show` | Active model across local/project/user |
| `claude-switch show <name>` | Profile detail |
| `claude-switch log` | Switch history |
| `claude-switch providers` | List providers |
| `claude-switch add ...` | Add profile |
| `claude-switch rm <name>` | Delete custom profile |
| `claude-switch add-provider <name> <url>` | Add custom provider |

## Built-in Providers

| Provider | Base URL | Env Key |
| --- | --- | --- |
| anthropic | native | `$ANTHROPIC_API_KEY` |
| deepseek | api.deepseek.com/anthropic | `$DEEPSEEK_API_KEY` |
| minimax | api.minimax.io/anthropic | `$MINIMAX_API_KEY` |
| openrouter | openrouter.ai/api | `$OPENROUTER_API_KEY` |

## Troubleshooting

### `ccs: claude not found`

Install Claude Code and confirm:

```bash
claude --help
```

### `tmux not found`

Install tmux:

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

## More Help

```bash
ccs --help
ccs --help-zh
claude-switch --help
claude-switch --help-zh
```
