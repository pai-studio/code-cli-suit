# cc-tmux

用 tmux 管理多个 Claude Code 会话，并允许每个会话使用不同的任意模型。

这里的“模型”指 `claude-switch` 的 profile/model，例如 `sonnet`、`opus`、`deepseek-flash`、`deepseek-v4-flash`、`openrouter/...` 等，而不是只限 Claude 原生 `--model` 支持的少数别名。

## 目标

`cc-tmux` 适合同时处理多个 Claude Code 工作流：

- 同一项目开多个 Claude 会话，每个会话使用不同模型
- 不同项目各自保持独立 Claude 会话
- 关闭 TUI 后，会话仍由 tmux 持续托管
- 随时附着回某个会话继续工作

核心策略：模型属于会话，不属于项目目录。

`cc-tmux` 不直接修改项目里的 `.claude/settings.json`。当你指定 `--cc-model` / `-m` 时，它会：

1. 调用 `claude-switch --dry-run <model>` 生成 settings JSON
2. 把 settings 写到当前会话自己的文件：`~/.cc-tmux/sessions/*.settings.json`
3. 用该 settings 文件启动 Claude：

```bash
claude --settings ~/.cc-tmux/sessions/<session>.settings.json --name <session>
```

这样同一个项目可以同时开多个不同模型的 Claude 会话，互不覆盖配置。

这些会话 settings 可能包含 provider token，因此文件会以 `0600` 权限写入，只允许当前用户读写。

## 安装

安装 tmux：

```bash
brew install tmux    # macOS
apt install tmux     # Linux
```

安装本项目：

```bash
pip install -e .
```

确认依赖可用：

```bash
cc-tmux --help
claude --help
claude-switch --help
```

如果要使用 DeepSeek、OpenRouter 等模型，需要先在 `claude-switch` 中有对应 profile，或直接使用它支持的内置 profile：

```bash
claude-switch list
claude-switch add dp deepseek-v4-pro -p deepseek
```

## TUI 使用

启动仪表盘：

```bash
cc-tmux tui
```

按键：

| 按键 | 功能 |
| --- | --- |
| `n` | 新建会话，可填写项目路径和 cc model/profile |
| `a` | 附着到选中的会话 |
| `k` | 销毁选中的会话 |
| `m` | 用新 cc model/profile 重启选中的会话 |
| `r` | 重命名选中的会话 |
| `R` | 刷新列表 |
| `Ctrl+d` | 销毁全部会话 |
| `q` | 退出 TUI |

列表中的 `Model` 列显示该会话当前绑定的 `claude-switch` profile/model。未指定模型的会话显示为 `default`，表示使用 Claude 自己的默认配置。

## CLI 使用

列出所有会话：

```bash
cc-tmux list
```

在当前目录新建默认模型会话：

```bash
cc-tmux new main -p .
```

在当前目录新建 Sonnet 会话：

```bash
cc-tmux new sonnet-work -p . --cc-model sonnet
```

`--cc-model` 也可以写成 `-m`：

```bash
cc-tmux new deepseek-fast -p . -m deepseek-flash
```

同一项目可以同时开多个模型：

```bash
cc-tmux new sonnet-impl -p . -m sonnet
cc-tmux new deepseek-review -p . -m deepseek-flash
cc-tmux new openrouter-test -p . -m openrouter/kimi-k2.6
```

这三个会话指向同一个项目目录，但各自使用独立 settings 文件。

附着到某个会话：

```bash
cc-tmux attach deepseek-review
```

用新模型重启已有会话：

```bash
cc-tmux model deepseek-review deepseek-v4-flash
```

注意：Claude Code 启动后不会自动重新读取模型配置。`cc-tmux model <name> <model>` 会重新生成该会话的 settings 文件，并重启对应 tmux window，让新模型生效。

切回默认配置：

```bash
cc-tmux model deepseek-review default
```

重命名会话：

```bash
cc-tmux rename deepseek-review api-review
```

销毁会话：

```bash
cc-tmux kill api-review
```

## 设计

- 所有 Claude 会话统一放在 tmux session：`cc-tmux`
- 每个用户会话对应一个 tmux window
- 模型配置由 `claude-switch --dry-run <model>` 生成
- 每个会话有自己的 settings 文件，避免同项目多会话互相覆盖
- Claude 通过 `claude --settings <session-settings>` 启动
- `cc-tmux model <name> <model>` 会重建 settings 并 `respawn-window`
- `_` 是内部占位窗口名，不能作为用户会话名

## 常见问题

### 为什么不用 `claude --model deepseek-v4-flash`？

Claude Code 的 `--model` 更适合原生别名或官方模型名，不负责切换 DeepSeek、OpenRouter 等 provider 的 base URL、token、alias 映射。

`claude-switch` 生成的 settings 可以包含这些内容，所以 `cc-tmux` 使用 `claude-switch --dry-run` 生成会话级 settings。

### 为什么不用 `claude-switch <model>` 直接改项目配置？

直接执行 `claude-switch <model>` 会写项目级 `.claude/settings.json`。同一个项目开多个会话时，后切换的模型会覆盖先前会话的项目配置。

`cc-tmux` 的做法是每个会话一份 settings 文件，所以同项目多模型可以并存。

### 修改模型为什么要重启 Claude？

运行中的 Claude 进程启动时已经读取了 settings。要让新模型生效，需要重启该进程。`cc-tmux model` 会自动重启对应 tmux window。

### 退出 TUI 后会话还在吗？

还在。Claude Code 运行在 tmux 中，退出 TUI 不会销毁会话。需要停止时执行：

```bash
cc-tmux kill <name>
```

### 如何直接进入 tmux？

```bash
tmux attach-session -t cc-tmux
```
