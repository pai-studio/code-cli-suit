"""Adapter contracts for code tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..store import CcsPaths, SessionRecord


@dataclass
class PreparedSession:
    command: list[str]
    cwd: str
    env: dict[str, str] = field(default_factory=dict)


class ToolAdapter(Protocol):
    id: str

    def prepare(self, session: SessionRecord, paths: CcsPaths) -> PreparedSession:
        ...
