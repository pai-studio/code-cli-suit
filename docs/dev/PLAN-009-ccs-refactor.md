# PLAN-009: ccs 按 v5 设计重构

> 日期: 2026-07-03
> 设计依据: `docs/design/ccs-user-interface-20260703-refactor.md`
> 目标: 不考虑旧兼容，把当前库重构为带标准化共享记忆的 Code CLI Suite。

## 1. 背景

当前代码仍以 `claude_switch` 为主包，包含旧的 tmux、TUI、daemon、session 管理和 legacy profile 逻辑。部分旧文件已经移动到历史备份目录，但主包仍处于半重构状态。

v5 设计已经明确：

- `ccs` 是统一启动 Claude Code / Codex / OpenCode 的命令行工具。
- 保留各 app 的原生参数。
- `ccs` 只新增默认模型、一次性模型覆盖、快速模式和项目共享记忆。
- 不保留旧 `claude-switch`、TUI、tmux、daemon、session 管理和私有 session 迁移。

## 2. 用户接口目标

首版实现这些公开命令：

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

其中 `<app>` 首版支持：

- `claude`
- `codex`
- `opencode`

## 3. 实施步骤

1. 新建 `ccs/` 主包，替代 `claude_switch/`。
2. 移动剩余旧 `claude_switch` 代码到 `docs/backup/`，不保留旧 console script。
3. 重写 `pyproject.toml`：
   - project name 改为 `ccs`
   - console script 只保留 `ccs = "ccs.cli:main"`
   - 移除 TUI 相关依赖
4. 实现核心模块：
   - `ccs/cli.py`: 命令入口和错误输出
   - `ccs/apps.py`: app spec、参数冲突检测、模式映射、LaunchPlan
   - `ccs/models.py`: provider/model registry，不读 legacy profile
   - `ccs/defaults.py`: `~/.ccs/config.toml` 默认模型
   - `ccs/memory.py`: `.ccs/memory.md` 布局、写入和命令
   - `ccs/settings.py`: Claude 运行时环境翻译
5. 重写 README，只保留 v5 主路径。
6. 重写测试：
   - 单元测试覆盖参数解析、模型解析、默认模型、模式映射、记忆写入。
   - 系统测试通过 fake app 验证真实 CLI 启动链路。
7. 运行系统测试：
   - `python -m unittest discover -s tests`
   - `python -m compileall ccs`
   - 必要的 dry-run/CLI smoke test
8. 对照设计稿复盘：
   - 标记实现与设计一致的部分。
   - 标记实现优于设计或设计优于实现的部分。
   - 选择最终保留方案并写入结果文档。

## 4. 非目标

- 不保留 `claude-switch` 命令。
- 不保留 `ccs tmux`、`ccs tui`、`ccs daemon`、`ccs list/attach/switch/kill/monitor`。
- 不读取 `~/.claude-switch-*` legacy profile。
- 不迁移私有 session。
- 不实现 `ccs handoff`、`ccs memory harvest`、`ccs memory compact` 的真实逻辑；只在设计中保留。

## 5. 验收条件

1. `python -m ccs --help` 显示新接口，不出现 tmux/TUI/daemon/claude-switch。
2. `ccs <app>` 只解析 `--cc-*`，非 `--cc-*` 原样透传。
3. 原生模型参数和 `--cc-model` 同时出现时报错。
4. `--cc-auto`、`--cc-danger`、`--cc-plan` 映射符合设计。
5. 不支持的快速模式明确报错。
6. `ccs use` 写 `~/.ccs/config.toml`，不写原工具配置。
7. `.ccs/memory.md` 可初始化、显示、追加 note/task/decision。
8. 默认启动注入项目记忆；`--cc-no-memory` 完全关闭记忆注入。
9. fake app 系统测试证明真实 CLI 启动链路可运行。
10. 结果文档完成设计与实现复盘。
