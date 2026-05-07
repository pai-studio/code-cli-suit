# claude-switch

Multi-provider model switcher for claude-code. Switch between Anthropic, DeepSeek, MiniMax, OpenRouter — like opencode.

> [中文文档](README_zh.md)

## Install

```bash
pip install .
```

Requires Python 3.10+. Zero dependencies.

## Setup

Set API keys in your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
# For built-in non-Anthropic models:
export DEEPSEEK_API_KEY="sk-xxx"
export OPENROUTER_API_KEY="sk-or-v1-xxx"
export MINIMAX_API_KEY="sk-xxx"
```

Then reload: `source ~/.zshrc`

If a key is missing, claude-switch will warn you when you switch.

## Quick Start

```bash
# Interactive picker
claude-switch

# Built-in profiles — no config needed, just set the env var:
claude-switch deepseek-pro       # DeepSeek v4 Pro  (via $DEEPSEEK_API_KEY)
claude-switch deepseek-flash     # DeepSeek v4 Flash
claude-switch minimax-m2.7       # MiniMax m2.7       (via $MINIMAX_API_KEY)
claude-switch openrouter/glm-5         # Zhipu GLM-5 @ OpenRouter (via $OPENROUTER_API_KEY)
claude-switch openrouter/kimi-k2.6     # Moonshot Kimi K2.6
claude-switch openrouter/gemini-flash  # Google Gemini 2.5 Flash

# Direct switch (Anthropic)
claude-switch sonnet

# Go back
claude-switch -
```

## Add Custom Profiles

```bash
# Simple: all aliases default to model name
claude-switch add my-pro deepseek-v4-pro -p deepseek

# Detailed: override specific aliases
claude-switch add my-pro deepseek-v4-pro -p deepseek --haiku deepseek-v4-flash

# OpenRouter example
claude-switch add or-sonnet anthropic/claude-sonnet-4-20250514 -p openrouter
```

## Commands

| Command | Description |
|---------|-------------|
| `claude-switch` | Interactive picker |
| `claude-switch <name>` | Switch by fuzzy name |
| `claude-switch -` | Back to previous |
| `claude-switch list` | List all profiles |
| `claude-switch show` | Active model (3 layers) |
| `claude-switch show <name>` | Profile detail |
| `claude-switch log` | Switch history |
| `claude-switch providers` | List providers |
| `claude-switch add ...` | Add profile |
| `claude-switch rm <name>` | Delete profile |
| `claude-switch add-provider <name> <url>` | Add custom provider |

## Scopes

| Flag | Scope | Path |
|------|-------|------|
| (default) | project | `<project>/.claude/settings.json` |
| `-l` | local | `<project>/.claude/settings.local.json` |
| `-u` | user | `~/.claude/settings.json` |

## Built-in Providers

| Provider | Base URL | Env Key |
|----------|----------|---------|
| anthropic | (native) | `$ANTHROPIC_API_KEY` |
| deepseek | api.deepseek.com/anthropic | `$DEEPSEEK_API_KEY` |
| minimax | api.minimax.io/anthropic | `$MINIMAX_API_KEY` |
| openrouter | openrouter.ai/api | `$OPENROUTER_API_KEY` |

Set keys in your shell:
```bash
export DEEPSEEK_API_KEY="sk-xxx"
export OPENROUTER_API_KEY="sk-or-v1-xxx"
```

## Advanced

```bash
claude-switch --dry-run dp     # preview JSON, don't write
claude-switch --preview dp     # confirm before writing
claude-switch --help           # full help
claude-switch --help-zh        # 中文帮助
```

## Docs

- [中文文档](README_zh.md)
- `claude-switch --help` / `claude-switch --help-zh`
