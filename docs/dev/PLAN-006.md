# PLAN-006: ccs 最终工作台方案

> 日期: 2026-05-08
> 状态: 设计中
> 目标: 一步到位实现低负担、多工具、多模型、多会话的可点击工作台

## 1. 背景

当前 `ccs` 已经实现了基于 tmux 的 Claude Code 会话管理：

- `ccs claude --cc-model <model>`
- `ccs list`
- `ccs attach`
- `ccs switch`
- `ccs kill`
- `ccs tui`

这个方案验证了核心模型：

```text
session = tool + model + project + args
```

但 tmux sidebar 的用户体验不符合最终目标：

- sidebar 是真实 tmux pane，会被用户误切进去。
- 左侧面板会抢空间、抢焦点。
- 鼠标点击 session 切换很难做成稳定体验。
- 用户需要理解 tmux pane/window/session，使用负担偏高。
- `ccs tui -> attach -> tmux` 会让主界面消失，心智模型断裂。

因此后续同时维护两条路线：

- 旧路线: tmux backend，作为 stable/legacy 路线继续保证可用。
- 新路线: `ccsd + workbench`，作为最终低负担体验推进。

旧路线继续修复明显体验问题，例如默认隐藏 sidebar、避免焦点落到 sidebar、用 ccs 自己的极简 picker 替代 tmux 原生 tree。新路线不再基于 tmux sidebar 扩展鼠标点击能力，而是构建 `ccs` 自己的工作台。

## 2. 产品目标

### 2.1 用户目标

用户只需要运行：

```bash
ccs
```

即可打开一个常驻工作台：

```text
┌──────────────────────┬──────────────────────────────────────────┐
│ Sessions             │ Claude / Codex / OpenCode                │
│                      │                                          │
│ ● api-review         │                                          │
│   claude ds/flash    │                                          │
│                      │                                          │
│   ui-fix             │                                          │
│   codex openai/gpt-5 │                                          │
│                      │                                          │
│ + New                │                                          │
└──────────────────────┴──────────────────────────────────────────┘
```

用户可以：

- 点击左侧 session 切换右侧终端。
- 点击 `+ New` 新建 session。
- 用键盘新建、切换模型、kill session。
- 退出工作台后 session 继续后台运行。
- 重新运行 `ccs` 后恢复并继续操作已有 session。

### 2.2 工程目标

- 支持 Claude Code、Codex、OpenCode。
- 每个 session 独立 tool/model/project/args/env。
- session 进程生命周期不绑定 TUI 前端。
- TUI 退出不杀 session。
- CLI 和 TUI 共用同一个 session backend。
- 不管理 API key，只读取环境变量。
- 保留现有 `provider/model` 模型规范。

## 3. 非目标

第一版最终工作台不做：

- 不做 API key 文件存储。
- 不做云同步。
- 不做多人协作。
- 不做浏览器 UI。
- 不做 tmux 作为默认交互层。
- 不做完整 shell multiplexing 替代品。
- 不做无限 scrollback，先做有界 buffer。

## 4. 架构选择

### 4.1 推荐架构

```text
┌─────────────┐
│ ccs CLI/TUI │
└──────┬──────┘
       │ Unix socket JSON RPC
┌──────▼──────┐
│ ccsd daemon │
└──────┬──────┘
       │ owns PTY master fds
┌──────▼─────────────────────────────────────────────┐
│ sessions                                             │
│  - claude + ds/flash + ~/repo + args                │
│  - codex + openai/gpt-5 + ~/repo2 + args            │
│  - opencode + or/kimi-k2.6 + ~/repo3 + args         │
└────────────────────────────────────────────────────┘
```

核心原则：

- daemon 拥有所有 PTY 和子进程。
- TUI 只是客户端，可以退出和重连。
- CLI 管理命令也通过 daemon 操作 session。
- 右侧终端渲染来自 daemon 返回的屏幕增量或 scrollback。

### 4.2 为什么不能只用 Textual 直接 fork PTY

如果在 Textual 进程内直接 `pty.fork()`：

- TUI 退出时 session 生命周期难以保证。
- `ccs list/kill/switch` 无法稳定管理后台 session。
- 重连已有 session 很困难。
- 进程异常退出时容易留下孤儿进程或丢失 PTY 状态。

因此一步到位必须引入 daemon。

### 4.3 tmux 的位置

tmux 后续作为 stable legacy backend：

- `ccs tmux ...` 或 `ccs legacy-tmux ...`
- 继续支持已有 `ccs tui/list/attach/switch/kill` 用户。
- 修复低成本、确定性的体验问题。
- 不在 tmux sidebar 上硬做点击切换 session。
- 不作为最终可点击工作台的实现基础。

维护原则：

- 不破坏已有命令。
- 不强制迁移旧用户。
- 新 workbench 成熟前，tmux backend 仍是可用主路径。
- 新 workbench 成熟后，tmux backend 变成显式兼容路径。

## 5. 用户接口定义

### 5.1 主入口

```bash
ccs
```

行为：

- 启动或连接 `ccsd`。
- 打开 Textual workbench。
- 如果没有 session，展示新建引导。
- 如果已有 session，默认选中最近使用的 session。

### 5.2 工作台快捷键

| Key | Action | 说明 |
| --- | --- | --- |
| 鼠标点击 session | switch | 切换右侧终端到该 session |
| `n` | new | 新建 session |
| `s` | switch model | 切换当前 session 模型并重启工具 |
| `k` | kill | 结束当前 session |
| `r` | restart | 用当前配置重启 session |
| `/` | filter | 过滤 session |
| `Tab` | focus terminal/sidebar | 在终端和侧栏之间切换焦点 |
| `F2` | sidebar | 聚焦 session 列表 |
| `F10` / `q` | leave | 退出工作台，session 继续运行 |
| `?` | help | 显示帮助 |

规则：

- 默认焦点在右侧终端。
- 点击左侧 session 后，切换 session，并自动把焦点还给右侧终端。
- `q` 的含义是离开工作台，不 kill session。
- kill 必须二次确认。

### 5.3 CLI 管理命令

主推交互式：

```bash
ccs
```

脚本和高级用户保留：

```bash
ccs new <tool> <provider/model> [tool args...]
ccs list [--json]
ccs attach <name>
ccs switch <name> [provider/model]
ccs restart <name>
ccs kill <name>
ccs models [provider]
ccs providers
```

示例：

```bash
ccs new claude ds/flash --permission-mode acceptEdits
ccs new codex openai/gpt-5
ccs new opencode or/kimi-k2.6
ccs switch api-review ds/pro
```

### 5.4 `ccs attach`

在新架构里，`attach` 不再 attach tmux，而是打开工作台并选中 session：

```bash
ccs attach api-review
```

行为：

- 连接 daemon。
- 打开 workbench。
- 选中 `api-review`。
- 右侧显示该 session 的终端。

### 5.5 原始工具参数

保留现有低负担规则：

```bash
ccs claude --cc-model ds/flash --permission-mode acceptEdits
```

规则：

- `--cc-*` 属于 ccs。
- 其他参数属于原始工具。

同时新增更短的显式创建形式：

```bash
ccs new claude ds/flash --permission-mode acceptEdits
```

两者等价方向：

```text
ccs claude --cc-model ds/flash ...  -> create or passthrough-compatible path
ccs new claude ds/flash ...         -> explicit managed session path
```

## 6. 数据模型

### 6.1 Session

```python
@dataclass
class SessionRecord:
    id: str
    name: str
    tool: str
    model: str
    project: str
    argv: list[str]
    env: dict[str, str]
    status: Literal["starting", "running", "exited", "failed"]
    pid: int | None
    exit_code: int | None
    created_at: str
    updated_at: str
    last_active_at: str
```

说明：

- `id` 是稳定内部 ID。
- `name` 是用户显示名，可自动生成，可改名。
- `model` 是 canonical `provider/model`，例如 `ds/flash`。
- `argv` 只保存工具参数，不保存 API key。
- `env` 只保存非敏感 session 环境覆盖；默认不保存 key。

### 6.2 RuntimeSession

daemon 内部运行态：

```python
@dataclass
class RuntimeSession:
    record: SessionRecord
    pid: int
    pty_fd: int
    screen: pyte.Screen
    stream: pyte.Stream
    scrollback: RingBuffer[str]
```

### 6.3 存储路径

```text
~/.ccs/
  ccsd.sock
  ccsd.pid
  sessions.json
  logs/
    ccsd.log
  settings/
    <session-id>.claude.settings.json
```

权限：

- `~/.ccs` 使用 `0700`
- session settings 使用 `0600`
- 不保存 API key

## 7. daemon 协议

第一版使用 Unix domain socket + newline-delimited JSON。

### 7.1 请求格式

```json
{
  "id": "req-1",
  "method": "session.list",
  "params": {}
}
```

### 7.2 响应格式

```json
{
  "id": "req-1",
  "ok": true,
  "result": {}
}
```

错误：

```json
{
  "id": "req-1",
  "ok": false,
  "error": {
    "code": "session_not_found",
    "message": "session 'api' not found"
  }
}
```

### 7.3 方法列表

| Method | Params | Result |
| --- | --- | --- |
| `daemon.ping` | `{}` | daemon info |
| `session.list` | `{}` | session records |
| `session.create` | tool/model/project/argv/name | session record |
| `session.kill` | name/id | ok |
| `session.restart` | name/id | session record |
| `session.switch_model` | name/id/model | session record |
| `session.activate` | name/id | session record |
| `terminal.snapshot` | name/id | screen snapshot |
| `terminal.input` | name/id/data | ok |
| `terminal.resize` | name/id/rows/cols | ok |
| `terminal.subscribe` | name/id | stream updates |

### 7.4 Terminal Snapshot

```json
{
  "cols": 120,
  "rows": 36,
  "cursor": {"x": 10, "y": 20, "visible": true},
  "lines": [
    {
      "text": "...",
      "spans": [
        {"start": 0, "end": 5, "fg": "#ffffff", "bg": null, "bold": true}
      ]
    }
  ]
}
```

第一版可以简化：

- daemon 维护 pyte screen。
- TUI 每 30ms 拉取 snapshot。
- 第二版再做增量推送。

## 8. Tool Adapter

每个工具由 adapter 负责生成命令和 session 配置。

### 8.1 接口

```python
class ToolAdapter(Protocol):
    id: str

    def build_command(self, session: SessionRecord) -> list[str]:
        ...

    def prepare(self, session: SessionRecord) -> PreparedSession:
        ...

    def validate_model(self, model: str) -> None:
        ...
```

### 8.2 Claude Adapter

输入：

```text
tool=claude
model=ds/flash
argv=["--permission-mode", "acceptEdits"]
```

行为：

- 解析 `ds/flash`
- 检查 `DEEPSEEK_API_KEY`
- 生成 `~/.ccs/settings/<id>.claude.settings.json`
- 启动：

```bash
claude --settings <settings> --name <name> --permission-mode acceptEdits
```

### 8.3 Codex Adapter

Codex 支持 OpenAI 以外模型的策略分两层：

1. 官方 OpenAI 路径：使用 Codex 原生配置。
2. 非 OpenAI 路径：优先通过 OpenAI-compatible endpoint/provider 配置。

计划接口：

```bash
ccs new codex openai/gpt-5
ccs new codex or/qwen3-coder
```

实现要求：

- 不假设 Codex 对所有 provider 原生支持。
- adapter 只负责把 `provider/model` 转成当前 Codex 可接受的配置。
- 如果某 provider 无法支持，明确报错：

```text
codex adapter does not support provider 'deepseek' yet
```

### 8.4 OpenCode Adapter

OpenCode 本身更接近 provider/model 模型，优先适配：

```bash
ccs new opencode or/kimi-k2.6
ccs new opencode ds/flash
```

具体 adapter 根据 opencode 当前配置方式实现。

## 9. Workbench UI

### 9.1 布局

```text
┌ Sessions ────────────┬ Terminal ─────────────────────────────────┐
│ filter: /            │                                          │
│                      │                                          │
│ ● api-review         │                                          │
│   claude ds/flash    │                                          │
│   ~/work/app         │                                          │
│                      │                                          │
│   ui-fix             │                                          │
│   codex openai/gpt-5 │                                          │
│   ~/work/ui          │                                          │
│                      │                                          │
│ + New                │                                          │
├──────────────────────┤                                          │
│ n new  s model       │                                          │
│ k kill q leave       │                                          │
└──────────────────────┴──────────────────────────────────────────┘
```

### 9.2 鼠标行为

- 点击 session row：activate session。
- 双击 session row：同单击，保持简单。
- 点击 `+ New`：打开新建弹窗。
- 点击终端：焦点进入终端。
- 点击 sidebar 后，完成动作立即恢复终端焦点。

### 9.3 新建弹窗

字段：

```text
Tool:    claude | codex | opencode
Model:   ds/flash
Project: .
Name:    optional
Args:    optional
```

默认：

- `Tool`: `claude`
- `Model`: `ds/flash`
- `Project`: 当前工作目录
- `Name`: 自动生成

### 9.4 模型切换弹窗

字段：

```text
Current: claude ds/flash
New model: ds/pro
```

行为：

- 更新 session record。
- 重新 prepare settings。
- kill 旧进程。
- spawn 新进程。
- terminal 重新连接到新 PTY。

## 10. 生命周期

### 10.1 daemon 启动

```text
ccs
  -> try connect ~/.ccs/ccsd.sock
  -> fail: spawn ccsd
  -> wait daemon.ping
  -> open workbench
```

### 10.2 session 创建

```text
Workbench new
  -> session.create
  -> daemon writes record
  -> adapter.prepare
  -> pty.fork
  -> exec tool
  -> return session
```

### 10.3 workbench 退出

```text
q/F10
  -> TUI exits
  -> daemon keeps running
  -> sessions keep running
```

### 10.4 daemon 退出

第一版策略：

- daemon 正常退出时，发送 SIGHUP 给所有子进程。
- 后续增加 `ccsd --shutdown --keep-sessions` 时再考虑脱管。

## 11. 兼容与迁移

### 11.1 现有 tmux session

第一版不自动迁移正在运行的 tmux session。

提供：

```bash
ccs tmux list
ccs tmux attach <name>
```

或者保留当前 tmux 命令一段时间。

### 11.2 现有模型映射

继续使用：

```text
~/.ccs/models.json
```

已有：

```bash
ccs models add or/qwen3-coder qwen/qwen3-coder
```

保持兼容。

### 11.3 命令兼容

保留：

```bash
ccs claude --cc-model ds/flash
```

但默认行为从 tmux-backed session 迁移为 daemon-backed session。

如果需要旧行为：

```bash
ccs tmux claude --cc-model ds/flash
```

## 12. 实施计划

### Phase 0: 优化并稳定当前 tmux 方案

目标：

- 先修复当前旧方案的高频体验问题。
- 标记为 legacy backend。
- 保留现有测试，避免回归。
- 允许多个终端窗口分别进入不同 session，不出现当前 window/input 同步。

任务：

- 默认关闭 sidebar，避免出现无关 pane。
- sidebar 只作为 `CCS_TMUX_SIDEBAR=1` 的兼容选项。
- F2 使用 ccs 极简 session picker，不直接暴露 tmux `choose-tree`。
- F2/F3/F4/F10 作为主推快捷键。
- 文档不再主推 `Ctrl-b n/p`。
- `ccs attach <name>` 不直接 attach 到共享后台 tmux session `ccs`。
- 为每个 code session 创建独立 grouped view session：

```text
ccs              # 后台 window 池，保存 code/review/... windows
ccs-view-code-*  # 终端 A 的独立视图
ccs-view-review-*# 终端 B 的独立视图
```

- `ccs attach code` 进入 `ccs-view-code-*`，`ccs attach review` 进入 `ccs-view-review-*`。
- view session 与后台 `ccs` 同组，共享真实 windows，但每个 client 有独立 current window。
- 这样避免两个终端同时 attach 到 `ccs` 时互相切换当前 window，导致输入看起来同步。
- 每个 Claude session 注入独立 `CLAUDE_CONFIG_DIR`，隔离 Claude Code 的 session history、UI 状态、credentials、plugins。
- `SessionManager` 改名或包装为 `TmuxSessionManager`。
- CLI 增加内部 backend 分支，但默认暂不切换。
- README 标注 tmux backend 是当前实现，不是最终工作台。

已落地：

- 默认 sidebar 关闭，`CCS_TMUX_SIDEBAR=1` 才启用。
- 默认 tmux mouse 关闭，`CCS_TMUX_MOUSE=1` 才启用。
- `ccs monitor [name...]` 用普通命令行观察多个 session 的最近输出，不 attach、不抢焦点。
- `ccs attach <name>` 使用 per-session grouped view session，避免多终端输入同步。
- `CLAUDE_CONFIG_DIR` 使用 `~/.ccs/sessions/<name-hash>.claude.config`，权限 `0700`。
- session settings 文件继续使用 `0600`。

### Phase 1: Daemon 基础

目标：

- 实现可启动、可连接、可创建 session 的 `ccsd`。

任务：

- 新增 `claude_switch/protocol.py`
- 新增 `claude_switch/daemon.py`
- 新增 `claude_switch/store.py`
- 实现 Unix socket JSON RPC。
- 实现 `daemon.ping/session.list/session.create/session.kill`。
- 实现 session metadata 持久化。

验收：

```bash
ccs daemon start
ccs daemon ping
ccs new claude ds/flash --cc-no-attach
ccs list
ccs kill <name>
```

### Phase 2: PTY Runtime

目标：

- daemon 拥有 PTY 和子进程。
- session 在 workbench 退出后继续运行。

任务：

- 从 b2 提取 PTY spawn/resize/input/render 逻辑。
- daemon 内维护 `RuntimeSession`。
- 实现 `terminal.input/resize/snapshot`。
- 有界 scrollback buffer。

验收：

- 创建 session 后 `ccs list` 显示 running。
- `ccs` 退出后进程继续存在。
- 再次 `ccs attach <name>` 能看到终端当前画面。

### Phase 3: Textual Workbench

目标：

- 实现左侧可点击 session 列表 + 右侧嵌入终端。

任务：

- 新增 `claude_switch/workbench.py`
- 新增 daemon client。
- 左侧 ListView 支持鼠标选择。
- 右侧 TerminalView 渲染 daemon snapshot。
- 键盘输入发送到 daemon。
- resize 同步到 daemon。

验收：

- 鼠标点击 session 可切换右侧终端。
- 点击后焦点自动回右侧终端。
- `q/F10` 离开工作台，session 继续运行。

### Phase 4: Tool Adapters

目标：

- 支持 Claude/Codex/OpenCode 三类工具。

任务：

- 新增 `claude_switch/adapters/base.py`
- 新增 `adapters/claude.py`
- 新增 `adapters/codex.py`
- 新增 `adapters/opencode.py`
- 统一 `provider/model` 解析入口。

验收：

```bash
ccs new claude ds/flash
ccs new codex openai/gpt-5
ccs new opencode or/kimi-k2.6
```

不可支持的 provider 必须清晰报错。

### Phase 5: CLI 迁移

目标：

- `ccs` 默认进入 workbench。
- 管理命令默认走 daemon。
- tmux backend 降级为 legacy。

任务：

- `ccs` 无参数打开 workbench。
- `ccs tui` alias 到 workbench。
- `ccs list/kill/switch` 调 daemon。
- `ccs tmux ...` 保留旧 backend。

验收：

```bash
ccs
ccs list
ccs attach <name>
ccs switch <name> ds/pro
ccs kill <name>
```

### Phase 6: 文档与安全

目标：

- 文档围绕最终用户目标，而不是实现细节。

任务：

- README 改成 workbench-first。
- `ccs --help` 展示最短使用路径。
- `ccs --help-zh` 同步中文说明。
- 安全文档明确不保存 API key。
- 增加故障恢复文档：

```bash
ccs daemon status
ccs daemon restart
ccs doctor
```

## 13. 测试计划

### 13.1 单元测试

- protocol encode/decode
- store atomic write
- model resolution
- adapter command building
- terminal key mapping
- session name auto generation

### 13.2 集成测试

- daemon start/ping/shutdown
- create/list/kill session
- PTY input/output roundtrip
- workbench headless mount
- click session activates terminal
- switch model restarts process

### 13.3 手工测试

必须覆盖：

- macOS Terminal.app
- iTerm2
- tmux 外部普通 shell
- 没有 API key 时的错误提示
- 工具不存在时的错误提示
- workbench 异常退出后 session 是否仍运行

## 14. 风险

### 14.1 Textual 终端渲染复杂度

风险：

- Claude/Codex/OpenCode 都是复杂 TUI 程序。
- ANSI、鼠标、光标、输入法、粘贴可能有兼容问题。

缓解：

- 第一版接受 80% 终端兼容。
- 保留 tmux legacy fallback。
- 优先支持键盘输入和基础 ANSI。

### 14.2 daemon 孤儿进程

风险：

- daemon 崩溃可能留下子进程。

缓解：

- 写 pid 文件。
- 启动时 reconcile sessions。
- `ccs doctor` 检查 orphan。

### 14.3 安全边界

风险：

- session settings 可能包含 provider endpoint 和模型配置。
- 不应保存 API key。

缓解：

- key 只从环境变量读取。
- settings 文件 `0600`。
- store 文件 `0600`。
- README 明确说明。

## 15. 决策记录

### 15.1 不继续强化 tmux sidebar

原因：

- 会抢焦点。
- 鼠标交互弱。
- 用户需要理解 tmux。
- 难以实现点击切换 session 后自动恢复 Claude 输入焦点。

### 15.2 引入 daemon

原因：

- session 生命周期必须独立于 TUI。
- 需要支持退出工作台后 session 继续运行。
- CLI/TUI 需要共享同一 backend。

### 15.3 `ccs` 作为唯一主入口

原因：

- 降低用户记忆负担。
- `ccs tui`、`ccs attach` 都是高级入口。
- 普通用户只需要 `ccs`。

## 16. 最小可交付切片

如果要最快落地最终方向，建议第一批 PR 只做：

1. `ccsd` daemon + socket ping。
2. daemon-backed Claude session create/list/kill。
3. Textual workbench 左侧点击 session。
4. 右侧 terminal snapshot/input。
5. `ccs` 无参数打开 workbench。

这会替代当前 tmux sidebar 的核心体验，并为 Codex/OpenCode adapter 留出稳定扩展点。
