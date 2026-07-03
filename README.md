# ccs

English | [中文](README.zh-CN.md)

`ccs` is a lightweight Code CLI Suite for launching Claude Code, Codex, and OpenCode with native arguments, fast model switching, quick launch modes, and shared project memory.

It does not wrap or redraw the original tool UI. It only helps with:

- preserving each tool's native command-line arguments
- setting per-app or global default models
- using one-shot model overrides
- mapping quick modes such as `--cc-auto`, `--cc-danger`, and `--cc-plan`
- sharing project memory through `.ccs/memory.md`

## Quick Start

```bash
pip install -e . --no-build-isolation

ccs memory init
ccs use claude ds/flash
ccs claude
```

## Launch Apps

```bash
ccs claude
ccs codex
ccs opencode
```

Arguments that are not prefixed with `--cc-` are passed through to the original app:

```bash
ccs claude --permission-mode plan
ccs codex --sandbox workspace-write "fix tests"
ccs opencode run "review this repo"
```

Native utility commands are passed through without model or memory injection:

```bash
ccs claude --help
ccs claude doctor
ccs codex --help
```

## Models

Use a model for one launch:

```bash
ccs claude --cc-model an/sonnet
ccs codex --cc-model openai/gpt-5
ccs opencode --cc-model or/kimi-k2.6
```

Set default models:

```bash
ccs use claude ds/flash
ccs use codex openai/gpt-5
ccs use opencode or/kimi-k2.6
ccs use ds/flash
ccs current
```

Model precedence:

```text
native app model flag > --cc-model > app default model > global default model > original app default
```

If `--cc-model` and a native model flag such as `--model` or `-m` are used in the same command, `ccs` reports a conflict.

## Quick Modes

```bash
ccs claude --cc-auto
ccs codex --cc-auto
ccs opencode --cc-auto

ccs claude --cc-danger
ccs codex --cc-danger
ccs opencode --cc-danger

ccs claude --cc-plan
```

Mode mapping:

| Mode | Claude | Codex | OpenCode |
| --- | --- | --- | --- |
| `--cc-auto` | `--permission-mode auto` | `--ask-for-approval never` | `--auto` |
| `--cc-danger` | `--dangerously-skip-permissions` | `--dangerously-bypass-approvals-and-sandbox` | `--auto` with a warning |
| `--cc-plan` | `--permission-mode plan` | unsupported | unsupported |

## Shared Memory

`ccs` uses `.ccs/memory.md` as the shared project memory across supported code CLIs.

```bash
ccs memory init
ccs memory note "Codex quota is exhausted; continue with Claude Code."
ccs memory task "Continue implementing defaults.py."
ccs memory decision "TUI is not part of the main interface."
ccs memory show
ccs memory status
ccs memory path
```

By default, `ccs <app>` injects a short memory prelude. Disable it for one launch:

```bash
ccs claude --cc-no-memory
```

`.ccs/memory.local.md` is ignored by default and is not injected by default.

## Models And Providers

```bash
ccs providers
ccs models
ccs models openrouter
ccs model show ds/flash
ccs models add or/qwen3-coder qwen/qwen3-coder
ccs models rm or/qwen3-coder
```

`ccs` does not store API keys. Provider commands only show whether the relevant environment variable is set.

## Development

Tests live under `tests/`:

```bash
python -m unittest discover -s tests
python -m compileall ccs
```

Historical code, experiments, and legacy README files are stored under `docs/backup/`.

## What It Does Not Do

- No TUI.
- No tmux session manager.
- No daemon.
- No private session migration.
- No API key storage.

