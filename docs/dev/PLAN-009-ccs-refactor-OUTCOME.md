# PLAN-009: ccs 按 v5/v6 设计重构结果

> 日期: 2026-07-03
> 计划文件: `docs/dev/PLAN-009-ccs-refactor.md`
> 设计文件: `docs/design/ccs-user-interface-20260703-refactor.md`
> 结果: 已完成

## 1. 完成内容

本次重构将主实现从 `claude_switch/` 切换为新的 `ccs/` 包。

新增主包：

```text
ccs/
  __init__.py
  __main__.py
  apps.py
  cli.py
  defaults.py
  errors.py
  memory.py
  models.py
  settings.py
```

公开入口：

```text
ccs <app> [--cc-model MODEL] [--cc-auto|--cc-danger|--cc-plan] [--cc-no-memory] [--cc-dry-run] [native args...]
ccs use [app] <model>
ccs current
ccs memory init|show|edit|note|task|decision|path|status
ccs models [provider]
ccs models add <provider/model> <actual-model>
ccs models rm <provider/model>
ccs providers
ccs model show <model>
```

## 2. 删除和归档

不再作为主包保留：

- `claude_switch/`
- `labs/b1-tmux-tui/`
- `labs/b2-pty-tui/`
- `README_zh.md`

相关旧代码已进入 `docs/backup/`：

- `docs/backup/claude_switch/`
- `docs/backup/claude_switch/active_legacy/`
- `docs/backup/labs/`
- `docs/backup/docs/`
- `docs/backup/assets/demo_extension_screenshot.png`

安装包不再包含 `docs/backup/`。

## 3. 关键实现

### 3.1 CLI 入口

`ccs/cli.py` 负责命令分发和用户级错误输出。旧命令如 `ccs tmux`、`ccs tui`、`ccs daemon` 不再保留行为，只提示当前 `ccs` 是 launcher。

### 3.2 AppSpec 和 LaunchPlan

`ccs/apps.py` 负责：

- app 名称和可执行文件
- 原生模型参数检测
- 快速模式映射
- 原生模式冲突检测
- provider 支持范围
- 记忆注入
- `LaunchPlan` 构造

### 3.3 模型和默认值

`ccs/models.py` 不再读取 `~/.claude-switch-*` legacy profile，只支持新的 provider/model：

- `an/sonnet`
- `ds/flash`
- `ds/pro`
- `openai/gpt-5`
- `or/kimi-k2.6`
- 以及 `ccs models add` 自定义映射

`ccs/defaults.py` 只写 `~/.ccs/config.toml` 或测试中的 `CCS_HOME/config.toml`，不写原工具配置。

### 3.4 共享记忆

`ccs/memory.py` 实现：

- `.ccs/memory.md`
- `.ccs/.gitignore`
- `ccs memory note|task|decision`
- `ccs memory path/status/show/edit`
- dry-run 不创建 `.ccs/memory.md`

## 4. 设计与代码比对

### 4.1 与设计一致

- app-first 入口：`ccs claude`、`ccs codex`、`ccs opencode`
- `--cc-*` 和原生参数分离
- 原生模型参数优先于默认模型
- `--cc-model` 和原生模型参数冲突时报错
- `--cc-auto`、`--cc-danger`、`--cc-plan` 互斥
- unsupported mode 明确报错
- 默认启用项目共享记忆
- `--cc-no-memory` 完全关闭记忆注入
- 不再保留 TUI、tmux、daemon、workbench、legacy profile

### 4.2 代码优于原设计的地方

1. `~/.ccs` 不能作为项目 memory root。
   - 原 v5 设计只说“向上查找最近 `.ccs/`”，实现测试发现这会把用户全局配置目录误当作项目记忆目录。
   - 已选择实现方案，并把设计更新为 v6：查找项目 `.ccs` 时跳过 `~/.ccs`，遇到 `.git/` 即停止并使用 git 根目录下的 `.ccs/`。

2. `--cc-dry-run` 应进入正式接口。
   - 原设计内部提到 `LaunchPlan` 可用于 dry-run，但主命令摘要遗漏。
   - 实现保留并正式化 `--cc-dry-run`，设计已更新为 v6。

3. 首版不拆 `injectors/` 包。
   - v5 设计建议 `injectors/claude.py|codex.py|opencode.py`。
   - 实现中 app 数量少，注入逻辑和 `AppSpec` 强相关，放在 `apps.py` 更直接、测试更简单。
   - 设计已更新为：复杂度上升后再拆 `injectors/`。

4. `codex exec` 和 `opencode run` 需要保留子命令形态。
   - 实现明确测试这两个子命令，记忆 prelude 会合并到子命令 message，而不是吞掉 `exec/run`。

### 4.3 设计优于当前代码、暂不实现的地方

- `ccs handoff <from-app> <to-app>`
- `ccs memory harvest <app>`
- `ccs memory compact`

这些仍保留为未来设计方向。当前选择是先把显式标准记忆做稳，不承诺私有 session 无损迁移。

## 5. 系统测试

已执行：

```bash
python -m unittest discover -s tests
```

结果：

```text
Ran 29 tests
OK
```

已执行：

```bash
python -m compileall ccs
```

结果：全部模块编译通过。

已执行 smoke test：

```bash
python -m ccs --help
python -m ccs models openai
python -m ccs claude --cc-model an/sonnet --cc-dry-run --cc-no-memory --permission-mode auto
python -m ccs codex --cc-model openai/gpt-5 --cc-danger --cc-dry-run "fix tests"
python -m ccs codex exec --cc-dry-run "fix tests"
python -m ccs opencode run --cc-dry-run "review repo"
```

结果：

- help 只展示新接口。
- `models openai` 正常显示 `openai/gpt-5`。
- Claude dry-run 展开 `--model sonnet`，未创建 memory。
- Codex danger dry-run 展开 `--dangerously-bypass-approvals-and-sandbox`。
- `codex exec` 和 `opencode run` 保留原生子命令，并合并记忆 prelude。

## 6. 最终选择

最终选择以实现后的 v6 设计为准：

- 主包使用 `ccs/`。
- 项目记忆使用 `.ccs/memory.md`。
- 全局配置使用 `~/.ccs/config.toml`。
- `~/.ccs` 不参与项目 memory root 查找。
- 首版不实现私有 session 迁移，只提供标准化共享记忆。
- 旧代码保存在 `docs/backup/`，不再进入安装包和测试契约。
