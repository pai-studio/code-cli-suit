# PLAN-007: `ccs opencode --cc-model` launcher

> 日期: 2026-05-08
> 状态: 历史计划，已由 `PLAN-009-ccs-refactor.md` 覆盖
> 目标: `ccs opencode --cc-model <model>` 正常工作，与 `ccs claude --cc-model <model>` 对等

## 0.1 后续状态

本计划描述的是旧 `claude_switch/ccs.py` 中的 OpenCode model 注入修复。当前仓库已经重构为新的 `ccs/` 主包，OpenCode model 注入由 `ccs/apps.py` 的 `AppSpec`/`LaunchPlan` 处理。

后续实现和验证以 `PLAN-009-ccs-refactor.md` 和 `PLAN-009-ccs-refactor-OUTCOME.md` 为准。本文仅作为历史分析记录保留。

## 0. 背景

`ccs` 已经声明支持 opencode：

- `TOOLS = {"claude", "codex", "opencode"}`（`ccs.py:225`）
- help 已写：`ccs opencode [opencode args...] [--cc-model MODEL]`
- `OpenCodeAdapter` 已存在（`adapters/generic.py:24-33`）
- `_launcher_command()` 已处理 opencode 分支（`ccs.py:1098-1099`）
- `--cc-dry-run` 和 passthrough args 路径已有

**但当前实现有 bug**：传 `--model` 时只传了 model name（如 `deepseek-v4-flash`），而 OpenCode 需要 `provider/model` 格式。

## 1. 问题分析

### 当前行为

```bash
ccs opencode --cc-model ds/flash
```

`_launcher_command()` 流程：

```
resolve_model_spec("ds/flash")
  → provider = "deepseek"
  → actual_model = "deepseek-v4-flash"
  → ["opencode", "--model", "deepseek-v4-flash"]   ← BUG: 缺 provider 前缀
```

OpenCode `--model` 解析（源码 `cli/cmd/run.ts:32`）按 `/` 分割为 `providerID/modelID`：

```typescript
function pick(value: string | undefined): ModelInput | undefined {
  const [providerID, ...rest] = value.split("/")
  return { providerID, modelID: rest.join("/") }
}
```

因此 `--model deepseek-v4-flash` 会被 OpenCode 解析为 `providerID="deepseek-v4-flash"`, `modelID=""` —— 找不到 provider。

### 需要的格式

```
anthropic/claude-sonnet-4-20250514
openai/gpt-5
deepseek/deepseek-chat
openrouter/moonshotai/kimi-k2.6
```

## 2. 修复方案

**唯一改动**：`_launcher_command()` 中 opencode 分支，将 `resolved.actual_model` 替换为 `{provider}/{actual_model}`。

### 代码变更

`claude_switch/ccs.py` L1098-1099：

```python
# 当前
if tool == "opencode":
    return ["opencode", "--model", resolved.actual_model, *passthrough], {}

# 改为
if tool == "opencode":
    model_str = f"{resolved.provider}/{resolved.actual_model}"
    return ["opencode", "--model", model_str, *passthrough], {}
```

### 效果对比

| ccs 命令 | 修复前 `opencode --model` | 修复后 |
|----------|--------------------------|--------|
| `--cc-model ds/flash` | `deepseek-v4-flash` | `deepseek/deepseek-v4-flash` |
| `--cc-model ds/pro` | `deepseek-v4-pro[1m]` | `deepseek/deepseek-v4-pro[1m]` |
| `--cc-model an/sonnet` | `sonnet` | `anthropic/sonnet` |
| `--cc-model an/opus` | `opus` | `anthropic/opus` |
| `--cc-model or/kimi-k2.6` | `moonshotai/kimi-k2.6` | `openrouter/moonshotai/kimi-k2.6` |
| `--cc-model mm/m2.7` | `minimax-m2.7` | `minimax/minimax-m2.7` |
| `--cc-model openai/gpt-5` | `gpt-5` | `openai/gpt-5` |

## 3. dry-run 验证

```
$ ccs opencode --cc-model ds/flash --cc-dry-run
backend: launcher
tool: opencode
name: (none)
project: /Users/xxx/current-dir
model: ds/flash
command: opencode --model deepseek/deepseek-v4-flash
managed: no
```

## 4. 前置条件（用户侧）

与 `ccs claude` 一致：ccs 只负责模型注入，不管理 API key。用户需在 OpenCode 的 provider 配置中设置 API key：

```jsonc
// ~/.config/opencode/opencode.json
{
  "provider": {
    "deepseek": {
      "apiKey": "sk-xxx",
      "baseURL": "https://api.deepseek.com/v1"
    }
  }
}
```

或通过环境变量（OpenCode 自动检测 `DEEPSEEK_API_KEY` 等）。

## 5. 非目标

- **不做** daemon / tmux session 管理（`ccs new opencode ...` / `ccs tmux opencode ...`）
- **不做** OpenCode provider 自动配置
- **不做** model.json 写入（`--model` flag 足够）
- **不做** cc-pty TUI 的 opencode 支持（后续独立 Plan）

## 6. 边界情况

| 输入 | 行为 |
|------|------|
| `ccs opencode --help` | **透传** — 无 `--cc-*` 参数时直接执行 `opencode --help` |
| `ccs opencode --cc-model ds/flash --cc-dry-run` | 打印命令，不执行 |
| `ccs opencode` (无参数) | 透传 `opencode`（使用 OpenCode 默认模型） |
| `ccs opencode --cc-model unknown/xyz` | `resolve_model_spec` 抛异常并提示 |

## 7. 文件变更

| 文件 | 行数 | 说明 |
|------|------|------|
| `claude_switch/ccs.py` | 1 行 | `_launcher_command()` L1099 修改 opencode 分支 |

无其他文件变更。
