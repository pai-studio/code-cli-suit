"""tmux-backed session management for ccs."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Optional

from . import profile_to_settings
from .models import resolve_model_spec, resolved_to_profile, validate_runtime_key


@dataclass
class CodeSession:
    name: str
    tool: str
    model: str
    project: str
    index: int
    pid: Optional[int]
    running: bool
    settings: str = ""
    config_dir: str = ""
    argv: list[str] | None = None

    @property
    def project_name(self) -> str:
        return Path(self.project).name if self.project else "?"

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "tool": self.tool,
            "model": self.model,
            "project": self.project,
            "project_name": self.project_name,
            "pid": self.pid,
            "running": self.running,
            "tmux_session": SessionManager.TMUX_SESSION,
            "tmux_window_index": self.index,
            "settings": self.settings,
            "config_dir": self.config_dir,
            "argv": self.argv or [],
        }


class SessionManager:
    """Manage code-tool sessions in a single tmux session."""

    TMUX_SESSION = "ccs"
    VIEW_SESSION_PREFIX = "ccs-view-"
    PLACEHOLDER = "_"
    TOOL_OPTION = "@ccs_tool"
    MODEL_OPTION = "@ccs_model"
    PROJECT_OPTION = "@ccs_project"
    SETTINGS_OPTION = "@ccs_settings"
    CONFIG_DIR_OPTION = "@ccs_config_dir"
    ARGV_OPTION = "@ccs_argv"
    MAIN_PANE_OPTION = "@ccs_main_pane"
    SIDEBAR_PANE_OPTION = "@ccs_sidebar_pane"
    SIDEBAR_WIDTH = 22
    SIDEBAR_ENV = "CCS_TMUX_SIDEBAR"
    MOUSE_ENV = "CCS_TMUX_MOUSE"

    def __init__(self) -> None:
        if not shutil.which("tmux"):
            raise RuntimeError("tmux not found")
        self._ensure_session()

    def _raw(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["tmux", *args],
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
        r = self._raw("has-session", "-t", self.TMUX_SESSION)
        if r.returncode != 0:
            self._tmux(
                "new-session",
                "-d",
                "-s",
                self.TMUX_SESSION,
                "-n",
                self.PLACEHOLDER,
            )
        self._configure_session_options(self.TMUX_SESSION)
        self._ensure_key_bindings()

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def list(self) -> list[CodeSession]:
        try:
            output = self._tmux(
                "list-windows",
                "-t",
                self.TMUX_SESSION,
                "-F",
                "#{window_index}\t#{window_name}\t#{pane_current_path}\t#{pane_pid}\t#{"
                + self.TOOL_OPTION
                + "}\t#{"
                + self.MODEL_OPTION
                + "}\t#{"
                + self.PROJECT_OPTION
                + "}\t#{"
                + self.SETTINGS_OPTION
                + "}\t#{"
                + self.CONFIG_DIR_OPTION
                + "}\t#{"
                + self.ARGV_OPTION
                + "}\t#{"
                + self.MAIN_PANE_OPTION
                + "}",
            )
        except RuntimeError:
            return []

        sessions: list[CodeSession] = []
        for line in output.splitlines():
            parts = line.strip().split("\t", 10)
            if len(parts) < 11:
                continue
            idx_s, name, pane_path, pid_s, tool, model, project, settings, config_dir, argv_s, main_pane = parts
            if name == self.PLACEHOLDER:
                continue
            if main_pane:
                main_info = self._main_pane_info(main_pane)
                if main_info is not None:
                    pane_path, pid_s = main_info
            pid = int(pid_s) if pid_s.isdigit() else None
            try:
                argv = json.loads(argv_s) if argv_s else []
            except json.JSONDecodeError:
                argv = []
            if not isinstance(argv, list):
                argv = []
            sessions.append(
                CodeSession(
                    name=name,
                    tool=tool or "?",
                    model=model or "default",
                    project=project or pane_path,
                    index=int(idx_s),
                    pid=pid,
                    running=self._pid_alive(pid) if pid else False,
                    settings=settings,
                    config_dir=config_dir,
                    argv=[str(a) for a in argv],
                )
            )
        return sessions

    def create_claude(
        self,
        *,
        name: Optional[str],
        project: str,
        model: Optional[str],
        passthrough: list[str],
        attach: bool,
        dry_run: bool,
    ) -> CodeSession | None:
        project_path = os.path.abspath(os.path.expanduser(project))
        if not os.path.isdir(project_path):
            raise RuntimeError(f"directory not found: {project_path}")

        resolved_model = resolve_model_spec(model or "default")
        session_name = name or self._next_name("claude", resolved_model.canonical, project_path)
        if name and any(session.name == name for session in self.list()):
            return self.switch_model(
                name=session_name,
                model=model,
                passthrough=passthrough if passthrough else None,
                attach=attach,
                dry_run=dry_run,
            )
        self._validate_new_name(session_name)

        settings = None
        if resolved_model.actual_model != "default":
            validate_runtime_key(resolved_model)
            settings = self._settings_path(session_name, "claude")
            self._write_claude_settings(model or "default", settings)

        argv = self._claude_argv(session_name, settings, passthrough)
        if dry_run:
            print(f"name: {session_name}")
            print(f"project: {project_path}")
            print(f"tool: claude")
            print(f"model: {resolved_model.canonical}")
            print(f"settings: {settings or '(default)'}")
            print(f"command: {self._shell_command(argv)}")
            return None

        self._tmux(
            "new-window",
            "-t",
            self.TMUX_SESSION,
            "-n",
            session_name,
            "-c",
            project_path,
            self._shell_command(argv),
        )
        target = f"{self.TMUX_SESSION}:{session_name}"
        main_pane = self._tmux("display-message", "-p", "-t", target, "#{pane_id}")
        self._set_window_metadata(
            target=target,
            tool="claude",
            model=resolved_model.canonical,
            project=project_path,
            settings=str(settings) if settings else "",
            config_dir="",
            argv=passthrough,
            main_pane=main_pane,
        )
        self._sync_sidebar(session_name)
        time.sleep(0.2)
        created = self._get(session_name)
        if attach:
            self.attach(session_name)
        return created

    def switch_model(
        self,
        *,
        name: str,
        model: Optional[str],
        passthrough: Optional[list[str]] = None,
        create: bool = False,
        project: str = ".",
        attach: bool = False,
        dry_run: bool = False,
    ) -> CodeSession | None:
        session = self._find(name)
        if session is None:
            if not create:
                raise RuntimeError(f"session '{name}' not found")
            return self.create_claude(
                name=name,
                project=project,
                model=model or "default",
                passthrough=passthrough or [],
                attach=attach,
                dry_run=dry_run,
            )
        if session.tool != "claude":
            raise RuntimeError(f"switch is not implemented for tool '{session.tool}'")
        if not os.path.isdir(session.project):
            raise RuntimeError(f"project '{session.project}' no longer exists")

        next_model = model or session.model
        resolved_model = resolve_model_spec(next_model)
        next_argv = session.argv or [] if passthrough is None else passthrough
        next_settings = None
        if resolved_model.actual_model != "default":
            validate_runtime_key(resolved_model)
            next_settings = self._settings_path(name, "claude")
            self._write_claude_settings(next_model, next_settings)

        argv = self._claude_argv(name, next_settings, next_argv)
        if dry_run:
            print(f"name: {name}")
            print(f"project: {session.project}")
            print("tool: claude")
            print(f"model: {resolved_model.canonical}")
            print(f"settings: {next_settings or '(default)'}")
            print(f"command: {self._shell_command(argv)}")
            return None

        target = f"{self.TMUX_SESSION}:{session.index}"
        old_settings = session.settings
        self._tmux(
            "respawn-window",
            "-k",
            "-t",
            target,
            "-c",
            session.project,
            self._shell_command(argv),
        )
        main_pane = self._tmux("display-message", "-p", "-t", target, "#{pane_id}")
        self._set_window_metadata(
            target=target,
            tool="claude",
            model=resolved_model.canonical,
            project=session.project,
            settings=str(next_settings) if next_settings else "",
            config_dir="",
            argv=next_argv,
            main_pane=main_pane,
        )
        self._sync_sidebar(name)
        if old_settings and old_settings != str(next_settings or ""):
            self._remove_settings(Path(old_settings))
        updated = self._get(name)
        if attach:
            self.attach(name)
        return updated

    def attach(self, name: Optional[str] = None) -> None:
        sessions = self.list()
        if not sessions:
            raise RuntimeError("no sessions")
        target_session = sessions[-1] if name is None else None
        if name is not None:
            for session in sessions:
                if session.name == name:
                    target_session = session
                    break
        if target_session is None:
            raise RuntimeError(f"session '{name}' not found")
        self._sync_sidebar(target_session.name)
        view_session = self._ensure_view_session(target_session.name)
        self._tmux("select-window", "-t", f"{view_session}:{target_session.index}")
        self.focus(target_session.name, tmux_session=view_session)
        if not os.environ.get("TMUX"):
            subprocess.run(["tmux", "attach-session", "-t", view_session])
        else:
            self._raw("switch-client", "-t", view_session)

    def select_relative(self, direction: str) -> CodeSession:
        sessions = self.list()
        if not sessions:
            raise RuntimeError("no sessions")
        if direction not in {"next", "prev"}:
            raise RuntimeError("direction must be 'next' or 'prev'")

        current_index = self._current_window_index()
        current_pos = 0
        for index, session in enumerate(sessions):
            if session.index == current_index:
                current_pos = index
                break
        step = 1 if direction == "next" else -1
        target = sessions[(current_pos + step) % len(sessions)]
        self.attach(target.name)
        return target

    def current_session_name(self) -> str | None:
        current_index = self._current_window_index()
        for session in self.list():
            if session.index == current_index:
                return session.name
        return None

    def capture(self, name: str, *, lines: int) -> str:
        session = self._find(name)
        if session is None:
            raise RuntimeError(f"session '{name}' not found")
        lines = max(1, lines)
        target = f"{self.TMUX_SESSION}:{session.index}"
        pane = self._window_option(target, self.MAIN_PANE_OPTION) or target
        return self._tmux("capture-pane", "-pJ", "-t", pane, "-S", f"-{lines}")

    def focus(self, name: Optional[str] = None, *, tmux_session: Optional[str] = None) -> None:
        session = self._find(name) if name is not None else None
        if name is None:
            current_index = self._current_window_index()
            for item in self.list():
                if item.index == current_index:
                    session = item
                    break
        if session is None:
            raise RuntimeError(f"session '{name}' not found" if name else "no current ccs session")
        target_session = tmux_session or self._current_tmux_session() or self.TMUX_SESSION
        if not self._session_in_ccs_group(target_session):
            target_session = self.TMUX_SESSION
        target = f"{target_session}:{session.index}"
        main_pane = self._window_option(target, self.MAIN_PANE_OPTION)
        if not main_pane:
            main_pane = self._tmux("display-message", "-p", "-t", target, "#{pane_id}")
            self._tmux("set-option", "-w", "-t", target, self.MAIN_PANE_OPTION, main_pane)
        self._tmux("select-window", "-t", target)
        self._raw("if-shell", "-F", f"#{{pane_in_mode}}", "send-keys -X cancel", "")
        self._tmux("select-pane", "-t", main_pane)

    def kill(self, name: str) -> None:
        for session in self.list():
            if session.name == name:
                settings = self._tmux(
                    "show-option",
                    "-wqv",
                    "-t",
                    f"{self.TMUX_SESSION}:{session.index}",
                    self.SETTINGS_OPTION,
                )
                self._tmux("kill-window", "-t", f"{self.TMUX_SESSION}:{session.index}")
                if settings:
                    self._remove_settings(Path(settings))
                return
        raise RuntimeError(f"session '{name}' not found")

    def _set_window_metadata(
        self,
        *,
        target: str,
        tool: str,
        model: str,
        project: str,
        settings: str,
        config_dir: str,
        argv: list[str],
        main_pane: str | None = None,
    ) -> None:
        values = {
            self.TOOL_OPTION: tool,
            self.MODEL_OPTION: model,
            self.PROJECT_OPTION: project,
            self.SETTINGS_OPTION: settings,
            self.CONFIG_DIR_OPTION: config_dir,
            self.ARGV_OPTION: json.dumps(argv),
        }
        if main_pane is not None:
            values[self.MAIN_PANE_OPTION] = main_pane
        for key, value in values.items():
            self._tmux("set-option", "-w", "-t", target, key, value)

    def _ensure_sidebar(self, name: str) -> None:
        session = self._find(name)
        if session is None:
            return
        target = f"{self.TMUX_SESSION}:{session.index}"
        main_pane = self._window_option(target, self.MAIN_PANE_OPTION)
        if not main_pane:
            main_pane = self._tmux("display-message", "-p", "-t", target, "#{pane_id}")
            self._tmux("set-option", "-w", "-t", target, self.MAIN_PANE_OPTION, main_pane)

        sidebar_pane = self._window_option(target, self.SIDEBAR_PANE_OPTION)
        if sidebar_pane and self._raw("display-message", "-p", "-t", sidebar_pane, "#{pane_id}").returncode == 0:
            self._tmux("select-pane", "-t", main_pane)
            return

        command = shlex.join(
            [
                sys.executable,
                "-m",
                "claude_switch.ccs",
                "sidebar",
                "--current",
                name,
                "--main-pane",
                main_pane,
            ]
        )
        sidebar_pane = self._tmux(
            "split-window",
            "-h",
            "-b",
            "-d",
            "-P",
            "-F",
            "#{pane_id}",
            "-l",
            str(self.SIDEBAR_WIDTH),
            "-t",
            main_pane,
            command,
        )
        self._tmux("set-option", "-w", "-t", target, self.SIDEBAR_PANE_OPTION, sidebar_pane)
        self._tmux("select-pane", "-t", main_pane)

    def _sync_sidebar(self, name: str) -> None:
        if self._sidebar_enabled():
            self._ensure_sidebar(name)
        else:
            self._remove_sidebar(name)

    def _remove_sidebar(self, name: str) -> None:
        session = self._find(name)
        if session is None:
            return
        target = f"{self.TMUX_SESSION}:{session.index}"
        sidebar_pane = self._window_option(target, self.SIDEBAR_PANE_OPTION)
        main_pane = self._window_option(target, self.MAIN_PANE_OPTION)
        if sidebar_pane and self._raw("display-message", "-p", "-t", sidebar_pane, "#{pane_id}").returncode == 0:
            self._raw("kill-pane", "-t", sidebar_pane)
        self._raw("set-option", "-w", "-u", "-t", target, self.SIDEBAR_PANE_OPTION)
        if main_pane:
            self._raw("select-pane", "-t", main_pane)

    @classmethod
    def _sidebar_enabled(cls) -> bool:
        return os.environ.get(cls.SIDEBAR_ENV, "").lower() in {"1", "true", "yes", "on"}

    @classmethod
    def _mouse_enabled(cls) -> bool:
        return os.environ.get(cls.MOUSE_ENV, "").lower() in {"1", "true", "yes", "on"}

    def _main_pane_info(self, pane_id: str) -> tuple[str, str] | None:
        r = self._raw("display-message", "-p", "-t", pane_id, "#{pane_current_path}\t#{pane_pid}")
        if r.returncode != 0:
            return None
        parts = r.stdout.strip().split("\t", 1)
        if len(parts) != 2:
            return None
        return parts[0], parts[1]

    def _window_option(self, target: str, key: str) -> str:
        return self._tmux("show-option", "-wqv", "-t", target, key)

    def _current_window_index(self) -> int | None:
        if os.environ.get("TMUX"):
            output = self._tmux("display-message", "-p", "#{window_index}")
        else:
            output = self._tmux("display-message", "-p", "-t", self.TMUX_SESSION, "#{window_index}")
        return int(output) if output.isdigit() else None

    def _current_tmux_session(self) -> str | None:
        r = self._raw("display-message", "-p", "#{session_name}")
        if r.returncode != 0:
            return None
        value = r.stdout.strip()
        return value or None

    def _ensure_view_session(self, name: str) -> str:
        view_session = self._view_session_name(name)
        r = self._raw("has-session", "-t", view_session)
        if r.returncode == 0:
            self._configure_session_options(view_session)
            return view_session
        self._tmux("new-session", "-d", "-t", self.TMUX_SESSION, "-s", view_session)
        self._configure_session_options(view_session)
        return view_session

    def _session_in_ccs_group(self, session_name: str) -> bool:
        if session_name == self.TMUX_SESSION:
            return True
        if not session_name.startswith(self.VIEW_SESSION_PREFIX):
            return False
        return self._raw("has-session", "-t", session_name).returncode == 0

    @classmethod
    def _view_session_name(cls, name: str) -> str:
        digest = sha1(name.encode("utf-8")).hexdigest()[:8]
        return f"{cls.VIEW_SESSION_PREFIX}{cls._slug(name)}-{digest}"

    def _configure_session_options(self, session_name: str) -> None:
        self._tmux("set-option", "-t", session_name, "mouse", "on" if self._mouse_enabled() else "off")
        self._ensure_status_bar(session_name)

    def _ensure_status_bar(self, session_name: str) -> None:
        self._tmux("set-option", "-t", session_name, "status", "on")
        self._tmux("set-option", "-t", session_name, "status-left-length", "24")
        self._tmux("set-option", "-t", session_name, "status-right-length", "120")
        self._tmux("set-option", "-t", session_name, "status-left", "[ccs] #W")
        self._tmux(
            "set-option",
            "-t",
            session_name,
            "status-right",
            "F2/C-b s sessions | F3/F4 prev/next | C-b i focus | Fn-Up/Fn-Down scroll | C-b [ j/k u/d g/G q | F10/C-b d leave",
        )

    def _ensure_key_bindings(self) -> None:
        session_check = f"#{{||:#{{==:#{{session_name}},{self.TMUX_SESSION}}},#{{m/r:^{self.VIEW_SESSION_PREFIX},#{{session_name}}}}}}"
        picker_command = shlex.join([sys.executable, "-m", "claude_switch.ccs", "pick"])
        next_command = shlex.join([sys.executable, "-m", "claude_switch.ccs", "select", "next"])
        prev_command = shlex.join([sys.executable, "-m", "claude_switch.ccs", "select", "prev"])
        focus_command = shlex.join([sys.executable, "-m", "claude_switch.ccs", "focus"])
        bindings = {
            "F2": f"display-popup -E -w 70% -h 60% {picker_command}",
            "F3": f"run-shell {shlex.quote(prev_command)}",
            "F4": f"run-shell {shlex.quote(next_command)}",
            "F10": "detach-client",
        }
        for key, command in bindings.items():
            self._tmux(
                "bind-key",
                "-n",
                key,
                "if-shell",
                "-F",
                session_check,
                command,
                f"send-keys {key}",
            )
        prefix_bindings = {
            "s": (f"display-popup -E -w 70% -h 60% {picker_command}", "choose-tree -Zw"),
            "n": (f"run-shell {shlex.quote(next_command)}", "next-window"),
            "p": (f"run-shell {shlex.quote(prev_command)}", "previous-window"),
            "i": (f"run-shell {shlex.quote(focus_command)}", "send-prefix"),
        }
        for key, (command, fallback) in prefix_bindings.items():
            self._tmux("bind-key", key, "if-shell", "-F", session_check, command, fallback)
        page_bindings = {
            "PPage": "copy-mode -u",
            "NPage": "copy-mode",
        }
        for key, command in page_bindings.items():
            self._tmux("bind-key", "-n", key, "if-shell", "-F", session_check, command, f"send-keys {key}")
        copy_mode_bindings = {
            "PPage": "send-keys -X page-up",
            "NPage": "send-keys -X page-down",
            "u": "send-keys -X halfpage-up",
            "d": "send-keys -X halfpage-down",
            "g": "send-keys -X history-top",
            "G": "send-keys -X history-bottom",
        }
        for key, command in copy_mode_bindings.items():
            self._tmux("bind-key", "-T", "copy-mode-vi", key, command)
            self._tmux("bind-key", "-T", "copy-mode", key, command)

    def _get(self, name: str) -> CodeSession:
        session = self._find(name)
        if session is not None:
            return session
        raise RuntimeError(f"session '{name}' created but not found")

    def _find(self, name: str) -> CodeSession | None:
        for session in self.list():
            if session.name == name:
                return session
        return None

    def _validate_new_name(self, name: str) -> None:
        if name == self.PLACEHOLDER:
            raise RuntimeError(f"session name '{self.PLACEHOLDER}' is reserved")
        if any(session.name == name for session in self.list()):
            raise RuntimeError(f"session '{name}' already exists")

    def _next_name(self, tool: str, model: str, project: str) -> str:
        base = "-".join(
            [
                self._slug(tool),
                self._slug(model),
                self._slug(Path(project).name or "project"),
            ]
        )
        existing = {session.name for session in self.list()}
        i = 1
        while f"{base}-{i}" in existing:
            i += 1
        return f"{base}-{i}"

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
        return slug or "x"

    @staticmethod
    def _claude_argv(
        name: str,
        settings: Optional[Path],
        passthrough: list[str],
    ) -> list[str]:
        argv = ["claude"]
        if settings:
            argv.extend(["--settings", str(settings)])
        if "--name" not in passthrough and "-n" not in passthrough:
            argv.extend(["--name", name])
        argv.extend(passthrough)
        return argv

    @staticmethod
    def _shell_command(argv: list[str], config_dir: Path | None = None) -> str:
        return shlex.join(["exec", *argv])

    @staticmethod
    def _state_dir() -> Path:
        base = os.environ.get("XDG_STATE_HOME")
        if base:
            return Path(base) / "ccs" / "sessions"
        return Path.home() / ".ccs" / "sessions"

    @classmethod
    def _settings_path(cls, name: str, tool: str) -> Path:
        digest = sha1(f"{tool}:{name}".encode("utf-8")).hexdigest()[:8]
        safe = cls._slug(name)
        return cls._state_dir() / f"{safe}-{digest}.{tool}.settings.json"

    @classmethod
    def _config_dir_path(cls, name: str, tool: str) -> Path:
        digest = sha1(f"{tool}:{name}".encode("utf-8")).hexdigest()[:8]
        safe = cls._slug(name)
        return cls._state_dir() / f"{safe}-{digest}.{tool}.config"

    @staticmethod
    def _ensure_config_dir(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)

    @staticmethod
    def _remove_settings(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _write_claude_settings(model: str, path: Path) -> None:
        resolved = resolve_model_spec(model)
        validate_runtime_key(resolved)
        data = profile_to_settings(resolved_to_profile(resolved))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        path.chmod(0o600)
