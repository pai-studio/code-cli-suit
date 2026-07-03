# ccs 用户接口重构设计

> 日期: 2026-07-03
> 状态: 设计稿 v6
> 主题: 带标准化共享记忆的 Code CLI Suite

## 1. 重新定位

`ccs` 的定位不是 session 管理器，也不是 TUI/Workbench 容器，而是：

> 面向 Claude Code / Codex / OpenCode 等 code CLI 的统一启动与协作工具。它保留各工具原始参数使用方式，同时提供统一的模型选择、默认模型切换、快速模式和跨 CLI 共享记忆。

这里的 `ccs` 建议解释为：

```text
Code CLI Suite
```

目标工具包括：

- `claude`
- `codex`
- `opencode`
- 后续其他 code CLI

经过试验，TUI 路线不作为当前产品接口继续推进。原因是 Claude Code 等工具本身不是开放 UI 组件，外部二次显示很难达到稳定、完整、低维护成本的体验。

## 2. 用户接口原则

1. `ccs` 不接管原工具 UI，只启动原工具。
2. 原工具参数保持原样，用户仍按 `claude`、`codex`、`opencode` 自己的文档使用参数。
3. app 是第一心智入口：`ccs claude ...`、`ccs codex ...`、`ccs opencode ...`。
4. `ccs` 自己的启动增强统一使用 `--cc-*` 参数，避免抢占原工具参数。
5. `ccs` 做四类增强：默认模型、一次性模型覆盖、快速模式、项目共享记忆。
6. 快速模式必须映射到各工具原生参数；没有原生等价参数时，不做伪装。
7. 危险模式必须显式命名，不能被普通自动模式悄悄包含。
8. 通过 `ccs` 启动的 app 默认共享一份标准化项目记忆。
9. 不承诺复制各工具私有 session，也不依赖私有 session 格式。
10. 不再暴露 `daemon`、`tui`、`workbench`、`pty`、`adapter`、`store`、`tmux session` 等内部概念。

## 3. 用户概念

| 概念 | 含义 | 示例 |
| --- | --- | --- |
| app | 要启动的 code CLI | `claude`, `codex`, `opencode` |
| model | `ccs` 统一模型名 | `ds/flash`, `openai/gpt-5`, `or/kimi-k2.6` |
| default model | 某个 app 的默认启动模型 | `claude -> ds/flash` |
| native args | 原工具自己的参数 | `--permission-mode plan`, `--sandbox workspace-write` |
| mode flag | `ccs` 提供的快速模式参数 | `--cc-auto`, `--cc-danger`, `--cc-plan` |
| project memory | 跨 app 共享的标准化记忆 | `.ccs/memory.md` |
| memory root | 当前项目记忆所在目录 | 最近的 `.ccs/` 或当前 git 根目录下的 `.ccs/` |

不进入用户接口的概念：

- daemon
- workbench
- TUI
- PTY
- tmux session
- adapter
- store
- legacy profile
- private session clone

## 4. 方案比较

### 方案 A: 只做 launcher

示例：

```bash
ccs claude --cc-model ds/flash --cc-auto
ccs codex --cc-model openai/gpt-5
```

优点：

- 范围小，容易实现。
- 行为接近当前代码。

缺点：

- 不能解决 Codex 额度用完后切到 Claude Code 继续工作的上下文断裂。
- 不能形成 `ccs` 相对原工具的长期核心价值。

结论：不够。保留 launcher 能力，但不是完整定位。

### 方案 B: 直接迁移各工具私有 session

示例：

```bash
ccs migrate-session codex claude
```

优点：

- 听起来最像“无缝切换”。
- 如果可行，用户负担最低。

缺点：

- Claude Code / Codex / OpenCode 的 session 格式和隐藏上下文不可稳定依赖。
- Claude Code 不是开放 UI/session 组件，私有格式可能随版本变化。
- “直接迁移 session”承诺过强，用户会误以为可以无损恢复工具调用历史和隐藏状态。

结论：不作为核心接口。未来可以做高级 `harvest`/`handoff`，但底层仍应转成标准记忆。

### 方案 C: `ccs` 维护标准化项目记忆

示例：

```bash
ccs claude --cc-auto
ccs memory note "Codex 额度用完，后续用 Claude Code 继续。"
ccs codex --cc-model openai/gpt-5
```

优点：

- 不依赖私有 session 格式。
- 记忆内容可读、可审计、可手动编辑。
- 所有 app 通过同一份 `.ccs/memory.md` 交换信息。
- 可以自然支撑未来 `ccs handoff codex claude`。

缺点：

- 不是无损 session 迁移。
- 需要约束记忆格式和注入方式。
- 自动更新记忆不能完全可靠，需要保留显式 `memory` 命令。

结论：采用。

## 5. 定稿接口

最终用户接口由 5 组命令组成：

```text
ccs <app> [--cc-model MODEL] [--cc-auto|--cc-danger|--cc-plan] [--cc-no-memory] [--cc-dry-run] [native args...]
ccs use [app] <model>
ccs current
ccs memory ...
ccs models/providers/model ...
```

辅助命令：

```text
ccs current
ccs memory init
ccs memory show
ccs memory edit
ccs memory note <text>
ccs memory task <text>
ccs memory decision <text>
ccs memory path
ccs memory status
ccs models
ccs providers
ccs model show <model>
ccs models add <provider/model> <actual-model>
ccs models rm <provider/model>
```

### 5.1 直接启动

```bash
ccs claude
ccs claude --permission-mode plan
ccs codex --sandbox workspace-write
ccs opencode --auto
```

行为：

- `ccs` 先判断这是不是一次 coding session 启动。
- `--help`、`auth`、`doctor`、`mcp` 等纯原生命令默认只透传，不注入模型，也不初始化记忆。
- coding session 启动时，`ccs` 查找该 app 的默认模型。
- 如果有默认模型，且原生参数没有显式指定模型，则注入模型参数或配置。
- app 参数全部保持原工具语义。
- 默认启用项目记忆：确保 `.ccs/memory.md` 存在，并向 app 注入记忆读取指令。
- 如果选定 app/mode 无法可靠注入记忆，默认报错；用户可用 `--cc-no-memory` 显式关闭。
- `--cc-dry-run` 只打印最终命令、工作目录、必要环境变量名称和 warning，不执行 app，也不创建 `.ccs/memory.md`。

### 5.2 一次性模型覆盖

```bash
ccs claude --cc-model ds/flash --permission-mode auto
ccs codex --cc-model openai/gpt-5 --sandbox workspace-write
ccs opencode --cc-model or/kimi-k2.6
```

行为：

- `--cc-model` 只对本次启动生效。
- 不修改默认模型配置。
- 如果 app 参数里也出现原生模型参数，例如 `--model` 或 `-m`，报冲突错误，避免双重模型来源。

### 5.3 切换默认模型

```bash
ccs use claude ds/flash
ccs use codex openai/gpt-5
ccs use opencode or/kimi-k2.6
ccs use ds/flash
ccs current
```

行为：

- `ccs use <app> <model>` 设置指定 app 的默认模型。
- `ccs use <model>` 设置全局默认模型。
- app 默认模型优先级高于全局默认模型。
- `ccs current` 显示全局默认模型和各 app 默认模型。
- `ccs use` 只写 `~/.ccs/config.toml`，不写原工具配置文件，不保存 API key。

覆盖规则：

```text
原生 app 模型参数 > --cc-model > app 默认模型 > 全局默认模型 > 原工具自身默认
```

说明：

- 原生 app 模型参数优先级最高，是为了保留各工具原始参数使用方式。
- 但原生模型参数不能和 `--cc-model` 同时出现；这属于同一次命令中重复表达模型，应报错。

### 5.4 快速模式

```bash
ccs claude --cc-auto
ccs codex --cc-auto
ccs opencode --cc-auto

ccs claude --cc-danger
ccs codex --cc-danger
ccs opencode --cc-danger

ccs claude --cc-plan
```

行为：

- `--cc-auto`、`--cc-danger`、`--cc-plan` 是 ccs 启动选项。
- 三者互斥，同一次启动只能出现一个。
- 快速模式只展开成该 app 的原生参数。
- 快速模式不改变默认模型。
- 如果某 app 不支持某快速模式，直接报错，不用 prompt 文案或伪配置模拟。

组合示例：

```bash
ccs claude --cc-model ds/flash --cc-auto --add-dir ../shared
ccs codex --cc-model openai/gpt-5 --cc-danger "fix tests"
ccs claude --cc-plan
```

### 5.5 项目共享记忆

```bash
ccs memory init
ccs memory show
ccs memory edit
ccs memory note "当前任务：重构 ccs 用户接口。"
ccs memory task "实现 --cc-auto 映射。"
ccs memory decision "TUI 路线不可行，旧代码归档到 backup。"
ccs memory path
ccs memory status
```

行为：

- `.ccs/memory.md` 是跨 app 共享的标准化项目记忆。
- `ccs <app>` 默认注入 `.ccs/memory.md`。
- `--cc-no-memory` 可关闭本次记忆注入和自动初始化。
- `memory.local.md` 用于本地临时记忆，默认不提交，也默认不注入。
- `ccs memory status` 显示当前 memory root、是否存在 `memory.md`、最近更新时间和是否启用本地文件。
- `ccs` 不承诺自动从私有 session 中恢复完整上下文。

预留增强接口：

```bash
ccs memory compact
ccs memory harvest <app>
ccs handoff <from-app> <to-app>
```

这些命令不进入首版必须实现范围。它们的设计目标是把公开 transcript、显式摘要或用户编辑内容转成标准记忆，而不是复制私有 session。

## 6. 项目记忆设计

### 6.1 文件布局

```text
.ccs/
  memory.md          # 标准化、人可读、可选提交的项目记忆
  memory.local.md    # 本地临时记忆，默认 gitignore，默认不注入
  events.jsonl       # ccs 启动和 memory 操作审计日志
  runtime/           # 每次启动生成的临时 prompt/settings
  .gitignore         # 忽略 local、runtime、events
```

全局用户配置放在用户目录，不放进项目 `.ccs/`：

```text
~/.ccs/
  config.toml        # 全局默认模型、app 默认模型
  models.json        # 用户自定义 provider/model 映射
```

默认 `.ccs/.gitignore`：

```gitignore
memory.local.md
events.jsonl
runtime/
```

设计理由：

- `memory.md` 是项目层共享记忆，可以按团队策略选择提交。
- 默认模型是用户偏好，不属于项目共享记忆，因此写入 `~/.ccs/config.toml`。
- `memory.local.md` 和运行日志默认不提交，降低泄漏风险。
- 所有文件都在 `.ccs/` 下，避免污染项目根目录。

### 6.2 `memory.md` 格式

第一版采用 Markdown，而不是 JSON/YAML。

原因：

- 所有 code CLI 都能自然读取和编辑 Markdown。
- 用户可审计、可手动修正。
- 不需要为每次小更新维护复杂 schema migration。

模板：

```md
# CCS Memory

## Goal
当前任务目标。

## Current State
当前代码状态、已完成内容。

## Notes
- 普通进展记录。

## Decisions
- [2026-07-03][ccs] 已做出的关键设计/实现决策。

## Open Tasks
- [ ] [2026-07-03][ccs] 下一步待办。

## Constraints
- 用户约束、项目约束、危险操作限制。

## Handoff Notes
### 2026-07-03 codex -> claude
- Objective:
- Completed:
- Next:
- Risks:
```

格式约束：

- 一级标题固定为 `# CCS Memory`。
- 二级标题固定，`ccs memory ...` 只在对应二级标题下追加内容。
- 新增记录默认带日期和来源 app，便于从 Codex 切到 Claude Code 时判断信息新旧。
- `memory.md` 不是密钥库；不要写 API key、token、cookie、私有证书。

### 6.3 记忆注入

`ccs` 启动 app 时，会渲染一段标准 prelude：

```text
You are launched by ccs.
Read and use the shared project memory at .ccs/memory.md.
When you make important decisions, finish meaningful work, or discover blockers,
update .ccs/memory.md, preferably by running `ccs memory note|task|decision`.
Do not store secrets there.
```

不同 app 的注入方式不同：

| app | 记忆注入方式 |
| --- | --- |
| `claude` | 优先用 `--append-system-prompt` 注入 prelude，并确保 `.ccs/` 在可读写目录内 |
| `codex` | 通过初始 prompt/prelude 注入；如果用户已有 prompt，则组合 prelude 和用户 prompt |
| `opencode` | 通过 `--prompt` 或初始 message 注入；run 模式可附加 `.ccs/memory.md` |

实现约束：

- 注入方式必须集中在 app spec 中，不散落在 CLI 解析逻辑里。
- 如果用户也传了原生 system prompt / prompt 参数，`ccs` 应按“ccs prelude 在前，用户原生 prompt 在后”的顺序组合；无法组合时直接报错。
- 如果某 app 的交互模式无法稳定注入 prelude，默认报错，而不是假装已注入。
- `--cc-no-memory` 必须完全关闭 prelude 注入。
- `memory.local.md` 首版不默认注入，避免用户把本地敏感信息误带入模型上下文。

### 6.4 记忆更新

第一版可靠路径是显式更新：

```bash
ccs memory note "Codex 额度用完，后续用 Claude Code 继续。"
ccs memory task "继续实现 defaults.py。"
ccs memory decision "模型配置只写 ~/.ccs/config.toml，不写原工具配置。"
```

启动时注入的 prelude 会鼓励 app 自己更新 `.ccs/memory.md`，但这不是强保证。

未来增强：

```bash
ccs memory harvest codex
ccs memory compact
ccs handoff codex claude
```

这些增强可以尝试读取公开日志或导出内容，但不应依赖私有 session 格式作为核心契约。

### 6.5 memory root 定位

`ccs` 必须让不同 app 在同一个项目里找到同一份记忆。定位规则：

1. 从当前工作目录向上查找最近的 `.ccs/`。
2. 查找时不能把用户全局配置目录 `~/.ccs` 当作项目 memory root。
3. 如果查找过程中先遇到 `.git/`，则在该 git 根目录创建 `.ccs/`，不继续向上搜索。
4. 如果既没有项目 `.ccs/` 也没有 `.git/`，在当前工作目录创建 `.ccs/`。
5. `ccs memory path` 必须输出最终使用的绝对路径。

设计理由：

- 用户通常在项目根目录或子目录启动 code CLI，向上查找能保证同项目共享一份记忆。
- 不要求用户先理解 project root 参数，简单路径保持 `ccs claude`。
- 显式路径通过 `ccs memory path/status` 可审计，避免隐藏写文件位置。
- `~/.ccs` 是全局配置目录，不能兼任项目共享记忆目录；否则会把无 git 项目或未初始化项目错误写到用户级目录。

### 6.6 写入契约和并发

首版写入分两类：

| 写入来源 | 契约 |
| --- | --- |
| `ccs memory ...` | 原子读改写 `memory.md`，并追加一条 `events.jsonl` |
| code CLI 自己编辑 | 允许，但不保证结构修复；prelude 应建议优先调用 `ccs memory ...` |

实现要求：

- `ccs memory ...` 使用临时文件 + rename 原子替换，避免半写入。
- 写入前后检查 `memory.md` 的修改时间；发现外部并发修改时重新读取再追加。
- `events.jsonl` 只用于本地审计和调试，默认不提交，不作为跨 CLI 共享数据源。
- 首版不做复杂 merge。如果结构损坏，`ccs memory status` 报告并提示用户手动修复。

### 6.7 启动链路

一次 `ccs claude --cc-model ds/flash --cc-auto` 的内部链路应是：

```text
parse argv
  -> identify app
  -> split ccs args and native args
  -> detect passthrough-only command
  -> resolve memory root
  -> resolve model
  -> build LaunchRequest
  -> AppSpec expands model/mode/native conflicts
  -> MemoryInjector renders prelude/runtime files
  -> LaunchPlan
  -> exec original app
```

核心内部类型建议：

```text
AppSpec
  name
  executable
  native_model_flags
  mode_mappings
  passthrough_patterns
  build_model_args()
  build_mode_args()
  inject_memory()

LaunchRequest
  app
  ccs_model
  quick_mode
  memory_policy
  native_args
  cwd

LaunchPlan
  executable
  argv
  env
  cwd
  runtime_files
  warnings
```

设计理由：

- `cli.py` 不应该知道 Claude/Codex/OpenCode 的参数细节。
- 模型注入、快速模式、记忆注入都属于 app 适配，但 `adapter` 不进入用户概念。
- `LaunchPlan` 可用于 `--cc-dry-run`、测试和错误提示，不必真的启动 app。

### 6.8 handoff 预留设计

`handoff` 解决的是“从一个 CLI 切到另一个 CLI 继续工作”的用户场景，但它不承诺私有 session 无损迁移。

预留接口：

```bash
ccs handoff codex claude
ccs handoff claude codex
```

语义：

1. 读取 `.ccs/memory.md`。
2. 如果 source app 有可公开读取的 transcript/export，则尝试生成摘要。
3. 如果没有公开 transcript，则打开编辑器或生成待填写模板。
4. 将摘要追加到 `## Handoff Notes`。
5. 打印下一步命令，例如 `ccs claude`。

首版不实现 `handoff` 的原因：

- 不同 CLI 的 transcript 可得性不同。
- 直接读私有 session 容易形成错误兼容承诺。
- 先把显式 memory 写入链路做稳，比追求“自动无损迁移”更重要。

### 6.9 记忆共享的安全边界

- `memory.md` 是项目共享上下文，不是私密数据库。
- `memory.local.md` 默认 gitignore，也默认不注入；它只能降低误提交风险，不能作为密钥保护机制。
- `ccs providers` 只能显示 key 是否存在，不能把 key 写入 memory。
- danger 模式、自动模式和记忆功能互不隐含：`--cc-danger` 不会额外扩大记忆读写范围。

## 7. 快速模式映射

下面映射基于当前本机 CLI help 验证，后续实现应集中放在 app spec 表中，便于随工具升级调整。

### 7.1 `--cc-auto`

含义：尽量减少常规确认，但不关闭安全边界。

| app | 映射 |
| --- | --- |
| `claude` | `--permission-mode auto` |
| `codex` | `--ask-for-approval never`，不自动改 sandbox |
| `opencode` | `--auto` |

设计理由：

- `--cc-auto` 是高效率模式，但不等于无沙箱。
- Codex 的 `--ask-for-approval never` 会减少确认；是否配合 `--sandbox` 由用户用原生参数决定。

### 7.2 `--cc-danger`

含义：跳过权限/沙箱确认，适合外部已经隔离好的环境。必须显式写 `--cc-danger`。

| app | 映射 |
| --- | --- |
| `claude` | `--dangerously-skip-permissions` |
| `codex` | `--dangerously-bypass-approvals-and-sandbox` |
| `opencode` | `--auto`，并在 dry-run/提示中标记该工具没有更强的统一 danger 参数 |

设计理由：

- `--cc-danger` 不能是 `--cc-auto` 的隐含升级。
- 如果 app 没有完全等价参数，必须在输出中说明实际展开结果。

### 7.3 `--cc-plan`

含义：只规划或优先规划，不直接执行修改。

| app | 映射 |
| --- | --- |
| `claude` | `--permission-mode plan` |
| `codex` | 暂不支持，除非未来确认原生参数 |
| `opencode` | 暂不支持，除非未来确认原生参数 |

设计理由：

- `--cc-plan` 不能用“追加提示词”伪造。那会改变用户输入语义，也不稳定。
- 不支持时给出明确错误：`--cc-plan is not supported for codex`。

## 8. 原生参数保留规则

新接口的核心边界：

```text
ccs <app> [native args... plus optional --cc-* args]
```

解析规则：

1. 第一个位置参数必须是 app 或 ccs 管理命令。
2. app 之后，只有 `--cc-*` 参数属于 `ccs`。
3. app 之后，所有非 `--cc-*` 参数都属于原工具，并按原顺序透传。
4. `--cc-*` 参数会被 `ccs` 解析并从传给原工具的 argv 中移除。
5. `--` 可接受但不是必需。

示例：

```bash
ccs claude --model sonnet
```

这里不报错，`--model sonnet` 完全属于 Claude 原生参数；如果存在 ccs 默认模型，本次也不注入默认模型。

```bash
ccs claude --cc-model ds/flash --model sonnet
```

这里应报冲突：`--cc-model ds/flash` 和原生 `--model sonnet` 同时指定了模型。

```bash
ccs claude --cc-plan --permission-mode auto
```

这里应报冲突：`--cc-plan` 和原生 `--permission-mode auto` 同时指定了 Claude 权限模式。

## 9. 模型注入设计

不同 app 的模型注入方式不同：

| app | 注入方式 |
| --- | --- |
| `claude` | 通过临时 `--settings` 或原生 `--model`，具体由实现选择，但用户接口不暴露 |
| `codex` | 原生 `--model <actual-model>` |
| `opencode` | 原生 `--model <provider>/<actual-model>` |

设计约束：

- 用户只看到 `ccs` 的统一 model spec。
- `ccs` 不管理各 app 的 API key。
- `ccs providers` 只能显示环境变量是否存在，不能打印 key。
- 某 app 不支持某 provider 时，应给出 app 维度错误，而不是模型解析错误。

## 10. 命令移除

这些不进入新用户接口：

```text
claude-switch ...
ccs tui
ccs tmux ...
ccs daemon ...
ccs new ...
ccs restart ...
ccs workbench ...
ccs list
ccs attach
ccs switch
ccs kill
ccs monitor
```

处理策略：

- `claude-switch` console script 不再注册。
- `ccs tui|tmux|daemon|new|restart|workbench` 返回 unknown command。
- 顶层 session 动词返回提示：`ccs is a launcher now. Use ccs <app> ...`。
- 相关旧代码统一进入 `docs/backup/`。

## 11. 错误设计

| 场景 | 错误 |
| --- | --- |
| app 不存在 | `unknown app 'x'. Supported apps: claude, codex, opencode.` |
| app 未安装 | `claude not found on PATH. Install it or choose another app.` |
| 模型不存在 | `unknown model 'x'. Run 'ccs models' to see available models.` |
| 快速模式不支持 app | `--cc-plan is not supported for codex.` |
| 多个快速模式同时出现 | `choose only one of --cc-auto, --cc-danger, --cc-plan.` |
| ccs 与原生同时指定模型 | `model is specified twice: --cc-model and native --model.` |
| ccs 与原生同时指定同类模式 | `mode is specified twice: --cc-plan and native --permission-mode.` |
| key 缺失 | `DEEPSEEK_API_KEY is not set for provider 'deepseek'.` |
| 记忆注入失败 | `memory injection is not supported for this app mode. Use --cc-no-memory or run ccs memory status.` |
| danger 模式 | dry-run 中必须显示展开后的危险参数 |

## 12. 文档结构

README 应按这个顺序重写：

1. `ccs` 是什么：带共享记忆的 code CLI suite。
2. Quick Start：`ccs memory init` + `ccs use claude ds/flash` + `ccs claude`。
3. 一次性模型覆盖：`ccs claude --cc-model ds/flash`。
4. 快速模式：`--cc-auto` / `--cc-danger` / `--cc-plan`。
5. 项目共享记忆：`.ccs/memory.md` 和 `ccs memory ...`。
6. 原生参数透传规则。
7. 模型和 provider。
8. 不做什么：不做 TUI、不做 session 管理、不保存 key、不复制私有 session。
9. Troubleshooting。

README 不再出现：

- `ccs tui`
- `ccs tmux`
- `claude-switch`
- daemon/workbench/panel

## 13. 对代码重构的约束

主包建议收敛为：

```text
ccs/
  __init__.py       # 包元信息
  __main__.py       # 指向 ccs
  cli.py            # CLI 入口和分发
  errors.py         # 统一错误类型
  apps.py           # app spec、快速模式映射、命令构造
  models.py         # provider/model 注册表
  defaults.py       # 默认模型配置读写
  memory.py         # 项目记忆布局、读写、命令
  settings.py       # Claude settings 翻译
```

不再保留在主包：

- `claude_switch/`
- `daemon.py`
- `protocol.py`
- `store.py`
- `session.py`
- `tui.py`
- `workbench.py`
- `adapters/`
- `labs/`

实现边界：

- `cli.py` 只解析 argv 并分发。
- `apps.py` 决定每个 app 如何注入模型和快速模式。
- `models.py` 只做模型解析，不读取旧 profile。
- `defaults.py` 只写 `ccs` 自己的默认模型配置。
- `memory.py` 只管理标准项目记忆，不解析私有 session。
- 首版记忆注入逻辑可以集中在 `apps.py` 的 `AppSpec`/`LaunchPlan` 构造中；等 app 数量或注入策略复杂到无法维护时，再拆出 `injectors/`。
- `settings.py` 只服务 Claude 运行时环境翻译。

## 14. 查漏补缺

### 第一轮：简单启动

```bash
ccs use claude ds/flash
ccs claude
```

结果：用户只需切一次默认模型，之后按原工具方式启动。

### 第二轮：原生参数

```bash
ccs claude --permission-mode plan
ccs codex --sandbox workspace-write
ccs opencode --auto
```

结果：app 后参数保持原生语义；如果没有 `--cc-*` 和默认模型，`ccs` 只是启动转发。

### 第三轮：快速模式

```bash
ccs claude --cc-auto
ccs codex --cc-danger
ccs claude --cc-plan
```

结果：高频模式短，危险模式显式，unsupported app 明确报错。

### 第四轮：记忆共享

```bash
ccs memory note "Codex 额度用完，后续用 Claude Code 继续。"
ccs claude --cc-auto
```

结果：Claude Code 启动时可读到标准记忆，不依赖 Codex 私有 session。

### 第五轮：未来扩展

新增 app 时只需要补：

- app 名称
- 可执行文件名
- 模型注入规则
- 快速模式映射
- 记忆注入策略
- 支持的 provider 范围

用户接口不需要增加新概念。

## 15. 最终结论

`ccs` 应重构为“默认模型 + 一次性模型覆盖 + `--cc-*` 快速模式 + 项目共享记忆”的 Code CLI Suite。

最终心智模型：

```bash
ccs memory init                  # 初始化标准记忆
ccs use claude ds/flash          # 设置默认模型
ccs claude                       # 快速启动 Claude Code，并注入 .ccs/memory.md
ccs claude --cc-model an/sonnet  # 本次覆盖模型
ccs claude --cc-auto             # 自动模式
ccs codex --cc-danger            # 危险跳过模式
ccs memory note "当前进展..."    # 写入跨 CLI 共享记忆
```

TUI、tmux、daemon 和旧兼容 CLI 都不属于当前用户接口，应进入 `docs/backup/`。私有 session 迁移不是核心契约，未来如实现，也应先转换为标准项目记忆。
