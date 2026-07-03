"""Textual session dashboard for ccs."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static
from textual.widgets.data_table import RowDoesNotExist

from .session import CodeSession, SessionManager


DEFAULT_TUI_MODEL = "ds/flash"
TuiAction = tuple[Literal["attach"], str]


@dataclass(frozen=True)
class NewSessionRequest:
    name: str | None
    project: str
    model: str
    passthrough: list[str]


def parse_new_session_request(
    *,
    name: str,
    project: str,
    model: str,
    args: str,
) -> NewSessionRequest:
    """Normalize the new-session modal payload."""
    try:
        passthrough = shlex.split(args)
    except ValueError as exc:
        raise RuntimeError(f"invalid Claude args: {exc}") from exc
    return NewSessionRequest(
        name=name.strip() or None,
        project=project.strip() or ".",
        model=model.strip() or DEFAULT_TUI_MODEL,
        passthrough=passthrough,
    )


class NewSessionScreen(ModalScreen[NewSessionRequest | None]):
    """Modal dialog for creating a Claude Code session."""

    CSS = """
    #dialog {
        padding: 1 2;
        width: 72;
        border: thick $primary;
        background: $surface;
    }
    #buttons { height: 3; align: center middle; }
    .title { text-style: bold; padding-bottom: 1; }
    Input { margin-bottom: 1; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("New Claude Session", classes="title")
            yield Input(placeholder="Session name (optional, auto-generated when empty)", id="name")
            yield Input(placeholder="Model, e.g. ds/flash, an/sonnet, or/kimi-k2.6", value=DEFAULT_TUI_MODEL, id="model")
            yield Input(placeholder="Project path", value=".", id="project")
            yield Input(placeholder="Claude args, e.g. --permission-mode acceptEdits", id="args")
            with Horizontal(id="buttons"):
                yield Button("Create", variant="primary", id="create")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#name", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "create":
            self.dismiss(None)
            return
        try:
            request = parse_new_session_request(
                name=self.query_one("#name", Input).value,
                model=self.query_one("#model", Input).value,
                project=self.query_one("#project", Input).value,
                args=self.query_one("#args", Input).value,
            )
        except RuntimeError as exc:
            self.app.notify(str(exc), severity="error", timeout=8)
            return
        self.dismiss(request)


class SwitchModelScreen(ModalScreen[str | None]):
    """Modal dialog for switching a session model."""

    CSS = NewSessionScreen.CSS

    def __init__(self, current: str) -> None:
        super().__init__()
        self.current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Switch Model", classes="title")
            yield Label(f"Current: {self.current}")
            yield Input(placeholder="New model, e.g. ds/pro, an/sonnet, or/kimi-k2.6", id="model")
            with Horizontal(id="buttons"):
                yield Button("Switch", variant="primary", id="switch")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#model", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "switch":
            self.dismiss(self.query_one("#model", Input).value.strip() or None)
        else:
            self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    """Simple confirmation dialog."""

    CSS = NewSessionScreen.CSS

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.message, classes="title")
            with Horizontal(id="buttons"):
                yield Button("Kill", variant="error", id="yes")
                yield Button("Cancel", variant="primary", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class HelpScreen(ModalScreen[None]):
    """Keyboard help dialog."""

    CSS = NewSessionScreen.CSS

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("ccs tui keys", classes="title")
            yield Static(
                "Enter  attach selected session\n"
                "n      new Claude session\n"
                "s      switch selected session model\n"
                "k      kill selected session\n"
                "r      refresh\n"
                "?      show this help\n"
                "q      quit"
            )
            with Horizontal(id="buttons"):
                yield Button("Close", variant="primary", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


class CcsTuiApp(App[TuiAction]):
    """Session dashboard backed by SessionManager."""

    BINDINGS = [
        Binding("n", "new_session", "New"),
        Binding("s", "switch_model", "Switch"),
        Binding("k", "kill_session", "Kill"),
        Binding("r", "refresh", "Refresh"),
        Binding("?", "help", "Help"),
        Binding("q", "quit", "Quit"),
    ]

    CSS = """
    DataTable { height: 1fr; }
    #empty {
        height: 3;
        padding: 1 2;
        color: $text-muted;
    }
    """

    def __init__(self, manager: SessionManager | None = None) -> None:
        super().__init__()
        self.manager = manager or SessionManager()
        self._sessions: list[CodeSession] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield DataTable(id="sessions")
        yield Static("", id="empty")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#sessions", DataTable)
        table.add_columns("Name", "Tool", "Model", "Project", "PID", "Status")
        table.cursor_type = "row"
        self._refresh()

    def _refresh(self, selected: str | None = None) -> None:
        table = self.query_one("#sessions", DataTable)
        table.clear()
        try:
            self._sessions = self.manager.list()
        except RuntimeError as exc:
            self.notify(str(exc), severity="error", timeout=10)
            self._sessions = []

        empty = self.query_one("#empty", Static)
        if not self._sessions:
            empty.update("No sessions. Press n to create a Claude session.")
            return
        empty.update("Enter attach  n new  s switch  k kill  r refresh  ? help  q quit")

        selected_row = 0
        for index, session in enumerate(self._sessions):
            status = "running" if session.running else "stopped"
            pid = str(session.pid or "-")
            table.add_row(
                session.name,
                session.tool,
                session.model,
                session.project_name,
                pid,
                status,
                key=session.name,
            )
            if selected and session.name == selected:
                selected_row = index
        if self._sessions:
            table.move_cursor(row=selected_row, column=0, animate=False)

    def _selected_session(self, *, silent: bool = False) -> CodeSession | None:
        table = self.query_one("#sessions", DataTable)
        try:
            row = table.get_row_at(table.cursor_row)
        except (IndexError, RowDoesNotExist, TypeError):
            if not silent:
                self.notify("No session selected", severity="warning")
            return None
        name = str(row[0])
        for session in self._sessions:
            if session.name == name:
                return session
        self.notify("Selected session no longer exists", severity="warning")
        return None

    def action_attach(self) -> None:
        session = self._selected_session()
        if session:
            self.exit(("attach", session.name))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        for session in self._sessions:
            if session.name == event.row_key.value:
                self.exit(("attach", session.name))
                return
        self.notify("Selected session no longer exists", severity="warning")

    @work
    async def action_new_session(self) -> None:
        self.push_screen(NewSessionScreen(), self._on_new_session)

    def _on_new_session(self, request: NewSessionRequest | None) -> None:
        if request is None:
            return
        try:
            session = self.manager.create_claude(
                name=request.name,
                project=request.project,
                model=request.model,
                passthrough=request.passthrough,
                attach=False,
                dry_run=False,
            )
        except RuntimeError as exc:
            self.notify(str(exc), severity="error", timeout=10)
            return
        selected = session.name if session else None
        self._refresh(selected=selected)
        if session:
            self.notify(f"Created {session.name}")

    def action_switch_model(self) -> None:
        session = self._selected_session()
        if session is None:
            return
        self.push_screen(SwitchModelScreen(session.model), lambda model: self._do_switch(session.name, model))

    def _do_switch(self, name: str, model: str | None) -> None:
        if not model:
            return
        try:
            session = self.manager.switch_model(name=name, model=model, attach=False)
        except RuntimeError as exc:
            self.notify(str(exc), severity="error", timeout=10)
            return
        self._refresh(selected=name)
        if session:
            self.notify(f"Switched {name} to {session.model}")

    def action_kill_session(self) -> None:
        session = self._selected_session()
        if session is None:
            return
        self.push_screen(
            ConfirmScreen(f"Kill session '{session.name}'?"),
            lambda ok: self._do_kill(session.name) if ok else None,
        )

    def _do_kill(self, name: str) -> None:
        try:
            self.manager.kill(name)
        except RuntimeError as exc:
            self.notify(str(exc), severity="error", timeout=10)
            return
        self._refresh()
        self.notify(f"Killed {name}")

    @work
    async def action_refresh(self) -> None:
        selected = self._selected_session(silent=True)
        self._refresh(selected=selected.name if selected else None)
        self.notify("Refreshed")

    def action_help(self) -> None:
        self.push_screen(HelpScreen())


def run_tui() -> TuiAction | None:
    """Run the ccs Textual dashboard."""
    return CcsTuiApp().run()
