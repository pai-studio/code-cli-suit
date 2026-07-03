"""Daemon-backed ccs workbench."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, OptionList, Static
from textual.widgets._option_list import Option

from .protocol import CcsClient, RpcError


class NewSessionScreen(ModalScreen[dict | None]):
    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("New Session", classes="title")
            yield Input(value="claude", placeholder="Tool: claude | codex | opencode", id="tool")
            yield Input(value="ds/flash", placeholder="Model: ds/flash", id="model")
            yield Input(value=".", placeholder="Project", id="project")
            yield Input(placeholder="Name (optional)", id="name")
            yield Input(placeholder="Tool args (optional)", id="args")
            with Horizontal(id="buttons"):
                yield Button("Create", variant="primary", id="create")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#model", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "create":
            self.dismiss(None)
            return
        import shlex

        self.dismiss(
            {
                "tool": self.query_one("#tool", Input).value.strip() or "claude",
                "model": self.query_one("#model", Input).value.strip() or "ds/flash",
                "project": self.query_one("#project", Input).value.strip() or ".",
                "name": self.query_one("#name", Input).value.strip() or None,
                "argv": shlex.split(self.query_one("#args", Input).value.strip()),
            }
        )


class SwitchModelScreen(ModalScreen[str | None]):
    def __init__(self, current: str) -> None:
        super().__init__()
        self.current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Current: {self.current}", classes="title")
            yield Input(placeholder="New model", id="model")
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


class ConfirmKillScreen(ModalScreen[bool]):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Kill session '{self.name}'?", classes="title")
            yield Label("Process will stop. Project files are not deleted.")
            with Horizontal(id="buttons"):
                yield Button("Kill", variant="error", id="kill")
                yield Button("Cancel", variant="primary", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "kill")


class TerminalPane(Static):
    can_focus = True

    def __init__(self, app_ref: "WorkbenchApp") -> None:
        super().__init__("")
        self.app_ref = app_ref

    def focus_on_click(self) -> bool:
        return True

    def on_key(self, event) -> None:
        if event.key in {"pageup", "page_up", "ctrl+up"}:
            self.app_ref.scroll_terminal(-10)
            event.stop()
            return
        if event.key in {"pagedown", "page_down", "ctrl+down"}:
            self.app_ref.scroll_terminal(10)
            event.stop()
            return
        if self.app_ref.read_only:
            return
        data = key_to_text(event)
        if data:
            self.app_ref.send_terminal_input(data)
            event.stop()


class WorkbenchApp(App):
    BINDINGS = [
        Binding("n", "new_session", "New", priority=True),
        Binding("s", "switch_model", "Model", priority=True),
        Binding("k", "kill_session", "Kill", priority=True),
        Binding("r", "restart_session", "Restart", priority=True),
        Binding("f2", "focus_sessions", "Sessions", priority=True),
        Binding("tab", "toggle_focus", "Focus", priority=True),
        Binding("f10", "quit", "Leave", priority=True),
        Binding("q", "quit", "Leave", priority=True),
        Binding("question_mark", "help", "Help", priority=True),
    ]

    CSS = """
    Screen { layout: vertical; }
    #body { height: 1fr; }
    #sidebar {
        width: 30;
        dock: left;
        border: solid $primary;
        height: 100%;
    }
    #session-list { height: 1fr; }
    #hints {
        height: auto;
        color: $text-muted;
        border-top: solid $primary;
        padding: 0 1;
    }
    TerminalPane {
        height: 100%;
        padding: 0 1;
        border: solid $primary;
        overflow: hidden;
    }
    TerminalPane:focus { border: double $accent; }
    #dialog {
        width: 58;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #buttons { height: 3; align: center middle; }
    .title { text-style: bold; padding-bottom: 1; }
    Input { margin-bottom: 1; }
    """

    def __init__(self, selected: str | None = None, *, read_only: bool = True) -> None:
        super().__init__()
        self.client = CcsClient()
        self.selected = selected
        self.read_only = read_only
        self.sessions: list[dict] = []
        self.session_by_id: dict[str, dict] = {}
        self._session_signature: tuple[tuple[str, str, str, str, str], ...] = ()
        self.terminal = TerminalPane(self)
        self.scroll_offset = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Label("Sessions")
                yield OptionList(id="session-list")
                yield Static(self._hint_text(), id="hints")
            yield self.terminal
        yield Footer()

    def on_mount(self) -> None:
        self.client.ensure_daemon()
        self.refresh_sessions()
        self.set_interval(1 / 15, self.refresh_terminal)
        self.terminal.focus()

    def refresh_sessions(self) -> None:
        sessions = self.client.call("session.list")
        signature = _session_signature(sessions)
        selected_before = self.selected
        self.sessions = sessions
        self.session_by_id = {session["id"]: session for session in self.sessions}
        if self.selected is None and self.sessions:
            self.selected = self.sessions[-1]["name"]
        if signature == self._session_signature and selected_before == self.selected:
            return
        self._session_signature = signature
        list_view = self.query_one("#session-list", OptionList)
        selected_id = self._selected_id()
        previous_highlight = list_view.highlighted
        list_view.clear_options()
        for session in self.sessions:
            active = session["id"] == selected_id
            list_view.add_option(Option(_session_prompt(session, active=active), id=session["id"]))
        if self.sessions:
            active_index = next(
                (index for index, session in enumerate(self.sessions) if session["id"] == selected_id),
                None,
            )
            if active_index is not None:
                list_view.highlighted = active_index
            elif previous_highlight is not None:
                list_view.highlighted = min(previous_highlight, len(self.sessions) - 1)

    def refresh_terminal(self) -> None:
        if not self.selected:
            self.terminal.update("No session selected.\nPress n to create one.")
            return
        try:
            height = max(10, self.size.height - 5)
            snap = self.client.call("terminal.snapshot", {"name": self.selected, "lines": height + self.scroll_offset})
        except RpcError as exc:
            self.terminal.update(f"Error: {exc}")
            return
        height = max(10, self.size.height - 5)
        width = max(20, self.size.width - 34)
        visible = self._visible_lines(snap["lines"], height)
        visible = format_terminal_lines(visible, width=width, height=height)
        suffix = f"\n\n-- scroll: {self.scroll_offset} lines above bottom --" if self.scroll_offset else ""
        self.terminal.update(Text("\n".join(visible) or "(no output yet)") + Text(suffix, style="dim"))

    def send_terminal_input(self, data: str) -> None:
        if not self.selected or self.read_only:
            return
        self.scroll_offset = 0
        self.client.call("terminal.input", {"name": self.selected, "data": data})

    def scroll_terminal(self, delta: int) -> None:
        self.scroll_offset = max(0, self.scroll_offset - delta)
        if delta < 0:
            self.scroll_offset = min(2000, self.scroll_offset)
        self.refresh_terminal()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        session_id = event.option.id
        if not isinstance(session_id, str):
            return
        session = self.session_by_id.get(session_id)
        if session is None:
            return
        self.selected = session["name"]
        self.scroll_offset = 0
        self._session_signature = ()
        try:
            self.client.call("session.activate", {"name": self.selected})
        except RpcError as exc:
            self.notify(str(exc), severity="error")
            return
        self.set_timer(0.05, self.refresh_sessions)

    def action_focus_sessions(self) -> None:
        self.query_one("#session-list", OptionList).focus()

    def action_toggle_focus(self) -> None:
        if self.terminal.has_focus:
            self.query_one("#session-list", OptionList).focus()
        else:
            self.terminal.focus()

    def action_help(self) -> None:
        self.notify(self._hint_text().replace("\n", " | "))

    def action_new_session(self) -> None:
        if self.read_only:
            self.notify("panel is read-only; use ccs new ...")
            return
        self.push_screen(NewSessionScreen(), self._create_session)

    def _create_session(self, values: dict | None) -> None:
        if not values:
            self.terminal.focus()
            return
        try:
            session = self.client.call("session.create", values)
        except RpcError as exc:
            self.notify(str(exc), severity="error")
            return
        self.selected = session["name"]
        self.scroll_offset = 0
        self.refresh_sessions()
        self.terminal.focus()

    def action_switch_model(self) -> None:
        if self.read_only:
            self.notify("panel is read-only; use ccs switch <name> <model>")
            return
        session = self.current_session()
        if not session:
            return
        self.push_screen(SwitchModelScreen(session["model"]), self._switch_model)

    def _switch_model(self, model: str | None) -> None:
        if not model or not self.selected:
            self.terminal.focus()
            return
        try:
            self.client.call("session.switch_model", {"name": self.selected, "model": model})
        except RpcError as exc:
            self.notify(str(exc), severity="error")
        self.refresh_sessions()
        self.terminal.focus()

    def action_restart_session(self) -> None:
        if self.read_only:
            self.notify("panel is read-only; use ccs restart <name>")
            return
        if not self.selected:
            return
        try:
            self.client.call("session.restart", {"name": self.selected})
        except RpcError as exc:
            self.notify(str(exc), severity="error")

    def action_kill_session(self) -> None:
        if self.read_only:
            self.notify("panel is read-only; use ccs kill <name>")
            return
        session = self.current_session()
        if session:
            self.push_screen(ConfirmKillScreen(session["name"]), self._kill_confirmed)

    def _kill_confirmed(self, confirmed: bool) -> None:
        if not confirmed or not self.selected:
            self.terminal.focus()
            return
        try:
            self.client.call("session.kill", {"name": self.selected})
        except RpcError as exc:
            self.notify(str(exc), severity="error")
        self.selected = None
        self.scroll_offset = 0
        self.refresh_sessions()
        self.terminal.focus()

    def current_session(self) -> dict | None:
        for session in self.sessions:
            if session["name"] == self.selected or session["id"] == self.selected:
                return session
        return None

    def _selected_id(self) -> str | None:
        for session in self.sessions:
            if session["name"] == self.selected or session["id"] == self.selected:
                return session["id"]
        return None

    def _visible_lines(self, lines: list[str], height: int) -> list[str]:
        if self.scroll_offset <= 0:
            return lines[-height:]
        end = max(0, len(lines) - self.scroll_offset)
        start = max(0, end - height)
        return lines[start:end]

    def _hint_text(self) -> str:
        if self.read_only:
            return "read-only panel\nF2/tab focus  Fn-Up/Down scroll  F10/q leave"
        return "n new  s model  k kill\nF2/tab focus  Fn-Up/Down scroll"


def _session_prompt(session: dict, *, active: bool) -> Text:
    marker = "*" if active else " "
    status = "run" if session.get("running") else session.get("status", "?")
    project = session.get("project_name") or Path(session.get("project", "")).name
    name = _clip(str(session["name"]), 24)
    model = _clip(f"{session['tool']} {session['model']}", 24)
    project_status = _clip(f"{project} [{status}]", 24)
    style = "bold cyan" if active else ""
    text = Text()
    text.append(f"{marker} {name}\n", style=style)
    text.append(f"  {model}\n", style="dim")
    text.append(f"  {project_status}", style="dim")
    return text


def _session_signature(sessions: list[dict]) -> tuple[tuple[str, str, str, str, str], ...]:
    return tuple(
        (
            str(session.get("id", "")),
            str(session.get("name", "")),
            str(session.get("tool", "")),
            str(session.get("model", "")),
            str(session.get("status", "")),
        )
        for session in sessions
    )


def format_terminal_lines(lines: list[str], *, width: int, height: int) -> list[str]:
    width = max(1, width)
    result = []
    for line in lines[-height:]:
        clean = line.expandtabs(4).rstrip()
        if len(clean) > width:
            clean = clean[: max(1, width - 1)] + "…"
        result.append(clean)
    return result[-height:]


def _clip(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    return value[: max(0, width - 1)] + "…"


def key_to_text(event) -> str:
    key = event.key
    if len(event.character or "") == 1:
        return event.character
    special = {
        "enter": "\r",
        "backspace": "\x7f",
        "tab": "\t",
        "escape": "\x1b",
        "up": "\x1b[A",
        "down": "\x1b[B",
        "right": "\x1b[C",
        "left": "\x1b[D",
        "home": "\x1b[H",
        "end": "\x1b[F",
        "pageup": "\x1b[5~",
        "page_up": "\x1b[5~",
        "pagedown": "\x1b[6~",
        "page_down": "\x1b[6~",
        "delete": "\x1b[3~",
    }
    if key in special:
        return special[key]
    if key.startswith("ctrl+") and len(key) == 6:
        return chr(ord(key[-1]) - 96)
    return ""


def run_workbench(*, selected: str | None = None, read_only: bool = True) -> None:
    WorkbenchApp(selected=selected, read_only=read_only).run()
