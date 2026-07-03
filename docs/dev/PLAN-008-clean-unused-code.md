# PLAN-008: 清理过期与未使用代码

> 日期: 2026-07-03
> 状态: 已被 `PLAN-009-ccs-refactor.md` 取代
> 目标: 不考虑旧兼容，把当前主线之外的实现统一移动到备份目录

## 0. 取代说明

本计划形成时仍把 `ccs tmux ...` 和 `ccs tui` 当作保留主线。后续设计已经调整为 `Code CLI Suite`：只保留 Claude Code / Codex / OpenCode 的快速启动、默认模型、`--cc-*` 快速模式和标准化项目记忆。

实际实施以 `PLAN-009-ccs-refactor.md` 和 `PLAN-009-ccs-refactor-OUTCOME.md` 为准。旧代码最终归档到 `docs/backup/`，而不是根目录 `backup/`。

## 1. 保留边界

当前主线只保留这些能力：

- `ccs claude --cc-model ...` 轻量 launcher
- `ccs codex --cc-model ...` 与 `ccs opencode --cc-model ...` 轻量 launcher
- `ccs tmux claude ...` 与 `ccs tmux list/attach/switch/kill/monitor`
- `ccs tui` 作为 tmux session 的可选 Textual 面板
- `ccs models/providers/model show` 模型与 provider 查询、模型映射增删

## 2. 归档边界

以下代码不再作为当前主线维护，移动到 `backup/`：

- 旧 `claude-switch` CLI 实现
- daemon / PTY / JSON-RPC / workbench 路线
- daemon 专用 adapters 与 store
- `labs/` 下的早期原型
- 旧 `README_zh.md`

## 3. 代码调整

- `claude_switch/__init__.py` 收敛为包元信息，不再承载旧 CLI。
- 新增 `claude_switch/settings.py` 存放当前 `ccs` 仍需要的 provider/profile/settings 翻译逻辑。
- `claude_switch/models.py` 不再读取旧 `~/.claude-switch-profiles.json`，只解析当前内置模型和 `ccs models add` 自定义映射。
- `claude_switch/ccs.py` 移除 daemon/new/restart/workbench 入口，顶层管理命令不再混用 daemon；tmux 管理必须显式走 `ccs tmux ...`。
- `pyproject.toml` 移除 `claude-switch` console script 和不再需要的 `pyte` 依赖。

## 4. 验证

- 更新测试，使测试覆盖当前主线。
- 运行 `python -m unittest test_ccs.py`。
- 使用 `rg` 检查 daemon/workbench/protocol/store/adapters 不再被主包引用。
