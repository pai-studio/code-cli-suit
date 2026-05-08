"""Generic adapters for tools that already accept model-like arguments."""

from __future__ import annotations

from ..models import ModelResolutionError, resolve_model_spec
from ..store import CcsPaths, SessionRecord
from .base import PreparedSession


class CodexAdapter:
    id = "codex"

    def prepare(self, session: SessionRecord, paths: CcsPaths) -> PreparedSession:
        resolved = resolve_model_spec(session.model)
        if resolved.provider not in {"openai", "openrouter"}:
            raise ModelResolutionError(f"codex adapter does not support provider '{resolved.provider}' yet")
        return PreparedSession(
            command=["codex", "--model", resolved.actual_model, *session.argv],
            cwd=session.project,
            env={},
        )


class OpenCodeAdapter:
    id = "opencode"

    def prepare(self, session: SessionRecord, paths: CcsPaths) -> PreparedSession:
        resolved = resolve_model_spec(session.model)
        return PreparedSession(
            command=["opencode", "--model", resolved.actual_model, *session.argv],
            cwd=session.project,
            env={},
        )
