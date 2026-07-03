# claude-switch

claude-code 多 provider 模型切换器。在 Anthropic、DeepSeek、MiniMax、OpenRouter 之间一键切换 — 像 opencode 一样。

## 安装

```bash
pip install .
```

需要 Python 3.10+，无第三方依赖。

## 设置

在 shell 配置文件（`~/.zshrc` 或 `~/.bashrc`）中设置 API Key：

```bash
# 非 Anthropic 模型需要对应的环境变量：
export DEEPSEEK_API_KEY="sk-xxx"
export OPENROUTER_API_KEY="sk-or-v1-xxx"
export MINIMAX_API_KEY="sk-xxx"
```

然后执行 `source ~/.zshrc` 生效。如果某个 Key 未设置，切换时会自动提醒。

## 快速上手

```bash
# 交互式选择
claude-switch

# 内置热门模型 — 一行切换，只需先设置好环境变量：
claude-switch deepseek-pro       # DeepSeek v4 Pro     (需 $DEEPSEEK_API_KEY)
claude-switch deepseek-flash     # DeepSeek v4 Flash
claude-switch minimax-m2.7       # MiniMax m2.7        (需 $MINIMAX_API_KEY)
claude-switch openrouter/glm-5         # 智谱 GLM-5 @ OpenRouter
claude-switch openrouter/kimi-k2.6     # Moonshot Kimi K2.6
claude-switch openrouter/gemini-flash  # Google Gemini 2.5 Flash

# 直接切换 (Anthropic)
claude-switch sonnet

# 回退到上一个
claude-switch -
```

## 添加自定义 Profile

```bash
# 简单模式：所有别名默认跟随模型名
claude-switch add my-pro deepseek-v4-pro -p deepseek

# 详细模式：覆盖指定别名
claude-switch add my-pro deepseek-v4-pro -p deepseek --haiku deepseek-v4-flash

# OpenRouter 示例
claude-switch add or-sonnet anthropic/claude-sonnet-4-20250514 -p openrouter
```

## 核心概念

| 概念 | 职责 | 示例 |
|------|------|------|
| **Provider** | 连接目标 (base_url + env_key) | deepseek, openrouter |
| **Profile** | 模型配置 (model + aliases) | deepseek-pro, sonnet |
| **Aliases** | `/model` 场景映射 | haiku→flash, opus→pro |

## 全部命令

| 命令 | 说明 |
|------|------|
| `claude-switch` | 交互式选择器 |
| `claude-switch <name>` | 模糊匹配切换 |
| `claude-switch -` | 回退到上一个 |
| `claude-switch list` | 列出所有 profile |
| `claude-switch show` | 三层覆盖状态 |
| `claude-switch show <name>` | 单个 profile 详情 |
| `claude-switch log` | 切换历史 |
| `claude-switch providers` | 列出 provider |
| `claude-switch add ...` | 添加 profile |
| `claude-switch rm <name>` | 删除 profile |
| `claude-switch add-provider <name> <url>` | 添加自定义 provider |

## 作用域

| Flag | 作用域 | 路径 |
|------|--------|------|
| (默认) | 项目级 | `<project>/.claude/settings.json` |
| `-l` | 本地级 | `<project>/.claude/settings.local.json` |
| `-u` | 用户级 | `~/.claude/settings.json` |

## 内置 Provider

| Provider | Base URL | 环境变量 |
|----------|----------|---------|
| anthropic | (原生) | `$ANTHROPIC_API_KEY` |
| deepseek | api.deepseek.com/anthropic | `$DEEPSEEK_API_KEY` |
| minimax | api.minimax.io/anthropic | `$MINIMAX_API_KEY` |
| openrouter | openrouter.ai/api | `$OPENROUTER_API_KEY` |

设置 API Key：
```bash
export DEEPSEEK_API_KEY="sk-xxx"
export OPENROUTER_API_KEY="sk-or-v1-xxx"
```

## 高级功能

```bash
claude-switch --dry-run dp     # 预览 JSON，不写入
claude-switch --preview dp     # 确认后再写入
claude-switch --help           # 英文帮助
claude-switch --help-zh        # 中文帮助
```

## 文档

- [English README](README.md)
- `claude-switch --help` / `claude-switch --help-zh`
