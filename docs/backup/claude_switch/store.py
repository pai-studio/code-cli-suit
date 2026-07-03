"""Persistent metadata store for daemon-backed ccs sessions."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal


SessionStatus = Literal["starting", "running", "exited", "failed"]


@dataclass
class SessionRecord:
    id: str
    name: str
    tool: str
    model: str
    project: str
    argv: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    status: SessionStatus = "starting"
    pid: int | None = None
    exit_code: int | None = None
    created_at: str = ""
    updated_at: str = ""
    last_active_at: str = ""

    @property
    def project_name(self) -> str:
        return Path(self.project).name if self.project else "?"

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "SessionRecord":
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            tool=str(data["tool"]),
            model=str(data["model"]),
            project=str(data["project"]),
            argv=[str(item) for item in data.get("argv", [])],
            env={str(k): str(v) for k, v in data.get("env", {}).items()},
            status=data.get("status", "exited"),
            pid=data.get("pid"),
            exit_code=data.get("exit_code"),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            last_active_at=str(data.get("last_active_at", "")),
        )


def now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class CcsPaths:
    """Filesystem locations for daemon-backed ccs state."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = home or self.default_home()
        self.socket = self.home / "ccsd.sock"
        self.pid = self.home / "ccsd.pid"
        self.sessions = self.home / "sessions.json"
        self.logs = self.home / "logs"
        self.settings = self.home / "settings"
        self.configs = self.home / "configs"

    @staticmethod
    def default_home() -> Path:
        override = os.environ.get("CCS_HOME")
        if override:
            return Path(override).expanduser()
        return Path.home() / ".ccs"

    def ensure(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.home.chmod(0o700)
        self.logs.mkdir(exist_ok=True)
        self.settings.mkdir(exist_ok=True)
        self.configs.mkdir(exist_ok=True)


class SessionStore:
    """Small JSON store for session records."""

    def __init__(self, paths: CcsPaths | None = None) -> None:
        self.paths = paths or CcsPaths()
        self.paths.ensure()

    def list(self) -> list[SessionRecord]:
        if not self.paths.sessions.exists():
            return []
        try:
            raw = json.loads(self.paths.sessions.read_text())
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        records = []
        for item in raw:
            if isinstance(item, dict):
                try:
                    records.append(SessionRecord.from_json(item))
                except (KeyError, TypeError, ValueError):
                    continue
        return records

    def save_all(self, records: list[SessionRecord]) -> None:
        self.paths.ensure()
        tmp = self.paths.sessions.with_suffix(".json.tmp")
        tmp.write_text(json.dumps([r.to_json() for r in records], indent=2, ensure_ascii=False) + "\n")
        tmp.replace(self.paths.sessions)

    def get(self, name_or_id: str) -> SessionRecord | None:
        for record in self.list():
            if record.name == name_or_id or record.id == name_or_id:
                return record
        return None

    def upsert(self, record: SessionRecord) -> None:
        records = self.list()
        for index, existing in enumerate(records):
            if existing.id == record.id:
                records[index] = record
                self.save_all(records)
                return
        records.append(record)
        self.save_all(records)

    def delete(self, name_or_id: str) -> SessionRecord | None:
        records = self.list()
        kept = []
        removed = None
        for record in records:
            if record.name == name_or_id or record.id == name_or_id:
                removed = record
            else:
                kept.append(record)
        if removed is not None:
            self.save_all(kept)
        return removed

    def make_record(
        self,
        *,
        tool: str,
        model: str,
        project: str,
        argv: list[str],
        name: str | None = None,
        env: dict[str, str] | None = None,
    ) -> SessionRecord:
        project_path = str(Path(project).expanduser().resolve())
        used = {record.name for record in self.list()}
        session_name = name or self._next_name(tool, model, project_path, used)
        if session_name in used:
            raise ValueError(f"session '{session_name}' already exists")
        stamp = now_ts()
        return SessionRecord(
            id=uuid.uuid4().hex,
            name=session_name,
            tool=tool,
            model=model,
            project=project_path,
            argv=argv,
            env=env or {},
            status="starting",
            created_at=stamp,
            updated_at=stamp,
            last_active_at=stamp,
        )

    @staticmethod
    def _next_name(tool: str, model: str, project: str, used: set[str]) -> str:
        base = "-".join([_slug(tool), _slug(model), _slug(Path(project).name or "project")])
        index = 1
        while f"{base}-{index}" in used:
            index += 1
        return f"{base}-{index}"


def _slug(value: str) -> str:
    import re

    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return slug or "x"
