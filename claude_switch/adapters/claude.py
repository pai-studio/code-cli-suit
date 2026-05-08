"""Claude Code adapter for daemon-backed sessions."""

from __future__ import annotations

import json
from pathlib import Path

from .. import profile_to_settings
from ..models import resolve_model_spec, resolved_to_profile, validate_runtime_key
from ..store import CcsPaths, SessionRecord
from .base import PreparedSession


class ClaudeAdapter:
    id = "claude"

    def prepare(self, session: SessionRecord, paths: CcsPaths) -> PreparedSession:
        resolved = resolve_model_spec(session.model or "default")
        env: dict[str, str] = {}
        argv = ["claude"]
        if resolved.actual_model != "default":
            validate_runtime_key(resolved)
            settings = paths.settings / f"{session.id}.claude.settings.json"
            settings.write_text(
                json.dumps(profile_to_settings(resolved_to_profile(resolved)), indent=2, ensure_ascii=False) + "\n"
            )
            settings.chmod(0o600)
            argv.extend(["--settings", str(settings)])
        if "--name" not in session.argv and "-n" not in session.argv:
            argv.extend(["--name", session.name])
        argv.extend(session.argv)
        return PreparedSession(command=argv, cwd=session.project, env=env)
