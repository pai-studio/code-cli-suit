"""Adapter registry."""

from __future__ import annotations

from .claude import ClaudeAdapter
from .generic import CodexAdapter, OpenCodeAdapter


def get_adapter(tool: str):
    adapters = {
        "claude": ClaudeAdapter(),
        "codex": CodexAdapter(),
        "opencode": OpenCodeAdapter(),
    }
    try:
        return adapters[tool]
    except KeyError:
        raise ValueError(f"unsupported tool '{tool}'") from None
