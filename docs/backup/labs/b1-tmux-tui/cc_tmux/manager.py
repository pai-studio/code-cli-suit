"""Tmux-based session management for Claude Code."""

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Optional


@dataclass
class Session:
    """A Claude Code session running in a tmux window."""

    name: str
    project: str
    model: str
    index: int
    pid: Optional[int]
    running: bool

    @property
    def project_name(self) -> str:
        return Path(self.project).name if self.project else "?"


class Manager:
    """Manage Claude Code sessions via tmux."""

    SESSION = "cc-tmux"
    PLACEHOLDER = "_"
    MODEL_OPTION = "@cc_model"
    SETTINGS_OPTION = "@cc_settings"

    def __init__(self):
        if not shutil.which("tmux"):
            raise RuntimeError("tmux not found — install: brew install tmux")
        self._ensure_session()

    # ------------------------------------------------------------------
    # Internal tmux helpers
    # ------------------------------------------------------------------

    def _raw(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["tmux"] + list(args),
            capture_output=True,
            text=True,
            timeout=10,
        )

    def _tmux(self, *args: str) -> str:
        r = self._raw(*args)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or f"tmux exited {r.returncode}")
        return r.stdout.strip()

    def _ensure_session(self) -> None:
        """Create the cc-tmux session if it doesn't exist yet."""
        r = self._raw("has-session", "-t", self.SESSION)
        if r.returncode != 0:
            self._tmux("new-session", "-d", "-s", self.SESSION, "-n", self.PLACEHOLDER)

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------

    def list(self) -> list[Session]:
        """Return all Claude Code windows in the cc-tmux session."""
        try:
            output = self._tmux(
                "list-windows",
                "-t",
                self.SESSION,
                "-F",
                "#{window_index}\t#{window_name}\t#{pane_current_path}\t#{pane_pid}\t#{"
                + self.MODEL_OPTION
                + "}",
            )
        except RuntimeError:
            return []

        sessions: list[Session] = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t", 4)
            if len(parts) < 5:
                continue
            idx_s, name, path, pid_s, model = parts
            if name == self.PLACEHOLDER:
                continue
            pid = int(pid_s) if pid_s.isdigit() else None
            running = self._pid_alive(pid) if pid else False
            sessions.append(
                Session(
                    name=name,
                    project=path,
                    model=model or "default",
                    index=int(idx_s),
                    pid=pid,
                    running=running,
                )
            )
        return sessions

    def new(
        self, name: str, project: str, model: Optional[str] = None
    ) -> Session:
        """Create a new tmux window running *claude* in *project*."""
        if name == self.PLACEHOLDER:
            raise RuntimeError(f"session name '{self.PLACEHOLDER}' is reserved")
        existing = [s for s in self.list() if s.name == name]
        if existing:
            raise RuntimeError(f"session '{name}' already exists")

        project = os.path.abspath(os.path.expanduser(project))
        if not os.path.isdir(project):
            raise RuntimeError(f"directory not found: {project}")

        settings = self._settings_path(name) if model and model != "default" else None
        if settings:
            self._write_model_settings(model, project, settings)

        self._tmux(
            "new-window",
            "-t",
            self.SESSION,
            "-n",
            name,
            "-c",
            project,
            self._claude_command(name, settings),
        )
        self._tmux(
            "set-option",
            "-w",
            "-t",
            f"{self.SESSION}:{name}",
            self.MODEL_OPTION,
            model or "default",
        )
        if settings:
            self._tmux(
                "set-option",
                "-w",
                "-t",
                f"{self.SESSION}:{name}",
                self.SETTINGS_OPTION,
                str(settings),
            )

        time.sleep(0.3)
        for s in self.list():
            if s.name == name:
                return s
        raise RuntimeError(f"session '{name}' created but not found in listing")

    def attach(self, name: str) -> None:
        """Bring a session window to the foreground."""
        for s in self.list():
            if s.name == name:
                self._tmux("select-window", "-t", f"{self.SESSION}:{s.index}")
                if not os.environ.get("TMUX"):
                    subprocess.run(
                        ["tmux", "attach-session", "-t", self.SESSION]
                    )
                return
        raise RuntimeError(f"session '{name}' not found")

    def kill(self, name: str) -> None:
        """Kill a session's tmux window."""
        for s in self.list():
            if s.name == name:
                settings = self._tmux(
                    "show-option",
                    "-wqv",
                    "-t",
                    f"{self.SESSION}:{s.index}",
                    self.SETTINGS_OPTION,
                )
                self._tmux("kill-window", "-t", f"{self.SESSION}:{s.index}")
                if settings:
                    self._remove_settings(Path(settings))
                return
        raise RuntimeError(f"session '{name}' not found")

    def set_model(self, name: str, model: str) -> None:
        """Restart a session with a different Claude model."""
        for s in self.list():
            if s.name == name:
                if not os.path.isdir(s.project):
                    raise RuntimeError(f"project '{s.project}' no longer exists")
                target = f"{self.SESSION}:{s.index}"
                old_settings = self._tmux(
                    "show-option",
                    "-wqv",
                    "-t",
                    target,
                    self.SETTINGS_OPTION,
                )
                settings = self._settings_path(name) if model != "default" else None
                if settings:
                    self._write_model_settings(model, s.project, settings)
                    settings_arg = str(settings)
                else:
                    settings_arg = ""
                self._tmux("set-option", "-w", "-t", target, self.MODEL_OPTION, model)
                self._tmux(
                    "set-option",
                    "-w",
                    "-t",
                    target,
                    self.SETTINGS_OPTION,
                    settings_arg,
                )
                self._tmux(
                    "respawn-window",
                    "-k",
                    "-t",
                    target,
                    "-c",
                    s.project,
                    self._claude_command(name, settings),
                )
                if old_settings and old_settings != settings_arg:
                    self._remove_settings(Path(old_settings))
                return
        raise RuntimeError(f"session '{name}' not found")

    def rename(self, old: str, new: str) -> None:
        """Rename a tmux window."""
        if new == self.PLACEHOLDER:
            raise RuntimeError(f"session name '{self.PLACEHOLDER}' is reserved")
        if any(s.name == new for s in self.list()):
            raise RuntimeError(f"session '{new}' already exists")
        for s in self.list():
            if s.name == old:
                old_settings = self._tmux(
                    "show-option",
                    "-wqv",
                    "-t",
                    f"{self.SESSION}:{s.index}",
                    self.SETTINGS_OPTION,
                )
                new_settings = ""
                if old_settings:
                    new_path = self._settings_path(new)
                    old_path = Path(old_settings)
                    if old_path.exists():
                        new_path.parent.mkdir(parents=True, exist_ok=True)
                        old_path.replace(new_path)
                    new_settings = str(new_path)
                self._tmux(
                    "rename-window", "-t", f"{self.SESSION}:{s.index}", new
                )
                if new_settings:
                    self._tmux(
                        "set-option",
                        "-w",
                        "-t",
                        f"{self.SESSION}:{new}",
                        self.SETTINGS_OPTION,
                        new_settings,
                    )
                return
        raise RuntimeError(f"session '{old}' not found")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _claude_command(name: str, settings: Optional[Path]) -> str:
        command = ["exec", "claude", "--name", name]
        if settings:
            command.extend(["--settings", str(settings)])
        return shlex.join(command)

    @staticmethod
    def _settings_dir() -> Path:
        base = os.environ.get("XDG_STATE_HOME")
        if base:
            return Path(base) / "cc-tmux" / "sessions"
        return Path.home() / ".cc-tmux" / "sessions"

    @classmethod
    def _settings_path(cls, name: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-") or "session"
        digest = sha1(name.encode("utf-8")).hexdigest()[:8]
        return cls._settings_dir() / f"{safe}-{digest}.settings.json"

    @staticmethod
    def _remove_settings(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _write_model_settings(model: str, cwd: str, path: Path) -> None:
        try:
            r = subprocess.run(
                ["claude-switch", "--dry-run", model],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("claude-switch not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("claude-switch timed out") from exc
        if r.returncode != 0:
            raise RuntimeError(
                f"claude-switch failed: {r.stderr.strip() or r.stdout.strip()}"
            )
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("claude-switch returned invalid JSON") from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")
        path.chmod(0o600)
