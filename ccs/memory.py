"""Shared project memory."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .errors import CcsError


MEMORY_TEMPLATE = """# CCS Memory

## Goal
当前任务目标。

## Current State
当前代码状态、已完成内容。

## Notes
- 普通进展记录。

## Decisions
- [YYYY-MM-DD][ccs] 已做出的关键设计/实现决策。

## Open Tasks
- [ ] [YYYY-MM-DD][ccs] 下一步待办。

## Constraints
- 用户约束、项目约束、危险操作限制。

## Handoff Notes
### YYYY-MM-DD source -> target
- Objective:
- Completed:
- Next:
- Risks:
"""

GITIGNORE_TEMPLATE = """memory.local.md
events.jsonl
runtime/
"""


@dataclass(frozen=True)
class MemoryPaths:
    root: Path
    memory: Path
    local: Path
    events: Path
    runtime: Path
    gitignore: Path


def resolve_memory_root(cwd: Path | str = ".") -> Path:
    start = Path(cwd).resolve()
    home_ccs = (Path.home() / ".ccs").resolve()
    for current in (start, *start.parents):
        candidate = current / ".ccs"
        if candidate.is_dir() and candidate.resolve() != home_ccs:
            return candidate
        if (current / ".git").exists():
            return current / ".ccs"
    return start / ".ccs"


def memory_paths(cwd: Path | str = ".") -> MemoryPaths:
    root = resolve_memory_root(cwd)
    return MemoryPaths(
        root=root,
        memory=root / "memory.md",
        local=root / "memory.local.md",
        events=root / "events.jsonl",
        runtime=root / "runtime",
        gitignore=root / ".gitignore",
    )


def init_memory(cwd: Path | str = ".") -> MemoryPaths:
    paths = memory_paths(cwd)
    paths.root.mkdir(parents=True, exist_ok=True)
    if not paths.memory.exists():
        _atomic_write(paths.memory, MEMORY_TEMPLATE)
    if not paths.gitignore.exists():
        _atomic_write(paths.gitignore, GITIGNORE_TEMPLATE)
    return paths


def prepare_memory(cwd: Path | str = ".", *, create: bool = True) -> MemoryPaths:
    return init_memory(cwd) if create else memory_paths(cwd)


def read_memory(cwd: Path | str = ".") -> str:
    paths = memory_paths(cwd)
    try:
        return paths.memory.read_text()
    except FileNotFoundError as exc:
        raise CcsError(f"memory not found at {paths.memory}. Run 'ccs memory init'.") from exc


def append_note(kind: str, text: str, cwd: Path | str = ".", *, source: str = "ccs") -> MemoryPaths:
    if kind not in {"note", "task", "decision"}:
        raise CcsError(f"unknown memory entry kind '{kind}'")
    body = text.strip()
    if not body:
        raise CcsError("memory text cannot be empty")

    paths = init_memory(cwd)
    content = paths.memory.read_text()
    section = {"note": "## Notes", "task": "## Open Tasks", "decision": "## Decisions"}[kind]
    today = datetime.now().strftime("%Y-%m-%d")
    if kind == "task":
        entry = f"- [ ] [{today}][{source}] {body}"
    else:
        entry = f"- [{today}][{source}] {body}"
    updated = _append_to_section(content, section, entry)
    _atomic_write(paths.memory, updated)
    _append_event(paths, kind, body, source)
    return paths


def edit_memory(cwd: Path | str = ".") -> int:
    paths = init_memory(cwd)
    editor = os.environ.get("EDITOR") or "vi"
    return subprocess.run([editor, str(paths.memory)]).returncode


def status(cwd: Path | str = ".") -> str:
    paths = memory_paths(cwd)
    exists = paths.memory.exists()
    mtime = "-"
    if exists:
        mtime = datetime.fromtimestamp(paths.memory.stat().st_mtime).isoformat(timespec="seconds")
    local = "present" if paths.local.exists() else "absent"
    return "\n".join(
        [
            f"memory root: {paths.root}",
            f"memory.md: {'present' if exists else 'missing'}",
            f"updated: {mtime}",
            f"memory.local.md: {local}",
        ]
    )


def prelude(paths: MemoryPaths) -> str:
    return (
        "You are launched by ccs.\n"
        f"Read and use the shared project memory at {paths.memory}.\n"
        "When you make important decisions, finish meaningful work, or discover blockers,\n"
        "update the shared memory, preferably by running `ccs memory note|task|decision`.\n"
        "Do not store secrets there."
    )


def _append_to_section(content: str, section: str, entry: str) -> str:
    lines = content.splitlines()
    try:
        start = lines.index(section)
    except ValueError:
        return content.rstrip() + f"\n\n{section}\n{entry}\n"

    insert_at = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## "):
            insert_at = idx
            break
    lines.insert(insert_at, entry)
    return "\n".join(lines).rstrip() + "\n"


def _append_event(paths: MemoryPaths, kind: str, text: str, source: str) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    line = f"{timestamp}\t{source}\t{kind}\t{text.replace(chr(9), ' ')}\n"
    paths.events.parent.mkdir(parents=True, exist_ok=True)
    with paths.events.open("a") as fh:
        fh.write(line)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text.rstrip() + "\n")
    tmp.replace(path)
