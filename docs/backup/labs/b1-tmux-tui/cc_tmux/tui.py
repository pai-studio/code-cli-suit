"""TUI dashboard for cc-tmux — Textual app with session table."""

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label
from textual.widgets.data_table import RowDoesNotExist

from .manager import Manager


# ===================================================================
# Modal screens
# ===================================================================


class NewSessionScreen(ModalScreen):
    """Modal dialog: create a new session."""

    def compose(self):
        with Vertical(id="dialog"):
            yield Label("New Claude Code Session", classes="title")
            yield Input(placeholder="Session name (e.g., feat-api)", id="name")
            yield Input(
                placeholder="Project path (e.g., . or ~/projects/app)", id="project", value="."
            )
            yield Input(
                placeholder="cc model/profile (optional, e.g., sonnet, deepseek-flash)",
                id="model",
            )
            with Horizontal(id="buttons"):
                yield Button("Create", variant="primary", id="create")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "create":
            self.dismiss(
                {
                    "name": self.query_one("#name", Input).value.strip(),
                    "project": self.query_one("#project", Input).value.strip(),
                    "model": self.query_one("#model", Input).value.strip() or None,
                }
            )
        else:
            self.dismiss(None)

    def on_mount(self):
        self.query_one("#name", Input).focus()


class ModelScreen(ModalScreen):
    """Modal: set model for a session."""

    def __init__(self, current: str = "?"):
        super().__init__()
        self._current = current

    def compose(self):
        with Vertical(id="dialog"):
            yield Label("Set Model", classes="title")
            yield Label(f"Current: {self._current}")
            yield Input(
                placeholder="cc model/profile (e.g., sonnet, deepseek-flash)",
                id="model",
            )
            with Horizontal(id="buttons"):
                yield Button("Set", variant="primary", id="set")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "set":
            self.dismiss(self.query_one("#model", Input).value.strip() or None)
        else:
            self.dismiss(None)

    def on_mount(self):
        self.query_one("#model", Input).focus()


class RenameScreen(ModalScreen):
    """Modal: rename a session."""

    def __init__(self, current: str):
        super().__init__()
        self._current = current

    def compose(self):
        with Vertical(id="dialog"):
            yield Label("Rename Session", classes="title")
            yield Label(f"Current: {self._current}")
            yield Input(placeholder="New session name", id="name")
            with Horizontal(id="buttons"):
                yield Button("Rename", variant="primary", id="rename")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "rename":
            self.dismiss(self.query_one("#name", Input).value.strip() or None)
        else:
            self.dismiss(None)

    def on_mount(self):
        self.query_one("#name", Input).focus()


class ConfirmScreen(ModalScreen):
    """Generic yes/no confirmation."""

    def __init__(self, message: str):
        super().__init__()
        self._message = message

    def compose(self):
        with Vertical(id="dialog"):
            yield Label(self._message, classes="title")
            with Horizontal(id="buttons"):
                yield Button("Yes", variant="error", id="yes")
                yield Button("No", variant="primary", id="no")

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(event.button.id == "yes")


# ===================================================================
# Main app
# ===================================================================


class TmuxApp(App):
    """Textual TUI for managing Claude Code sessions via tmux."""

    BINDINGS = [
        Binding("n", "new_session", "New", priority=True),
        Binding("a", "attach", "Attach", priority=True),
        Binding("k", "kill", "Kill", priority=True),
        Binding("m", "model", "Model", priority=True),
        Binding("r", "rename", "Rename", priority=True),
        Binding("R", "refresh", "Refresh", priority=True),
        Binding("ctrl+d", "kill_all", "Kill All", priority=True),
        Binding("q", "quit", "Quit", priority=True),
    ]

    CSS = """
    DataTable { height: 1fr; }
    DataTable > .datatable--header { text-style: bold; }

    /* Modal dialog styling */
    #dialog {
        padding: 1 2;
        width: 52;
        min-height: 10;
        border: thick $primary;
        background: $surface;
    }
    #buttons { height: 3; align: center middle; }
    .title { text-style: bold; padding-bottom: 1; }
    Input { margin-bottom: 1; }
    """

    def __init__(self):
        super().__init__()
        self.manager = Manager()

    def compose(self):
        yield Header(show_clock=False)
        yield DataTable()
        yield Footer()

    def on_mount(self):
        table = self.query_one(DataTable)
        table.add_columns("Name", "Project", "Model", "PID", "Status")
        table.cursor_type = "row"
        self._refresh()

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------

    def _refresh(self):
        table = self.query_one(DataTable)
        table.clear()
        try:
            sessions = self.manager.list()
        except RuntimeError as exc:
            self.notify(str(exc), severity="error", timeout=10)
            return
        for s in sessions:
            icon = "●" if s.running else "○"
            table.add_row(s.name, s.project_name, s.model, str(s.pid or ""), icon)

    def _selected_session(self) -> str | None:
        """Return the name of the currently selected row, or None."""
        table = self.query_one(DataTable)
        try:
            row = table.get_row_at(table.cursor_row)
            return str(row[0])
        except (IndexError, RowDoesNotExist, TypeError):
            self.notify("No session selected", severity="warning")
            return None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @work
    async def action_new_session(self):
        self.push_screen(NewSessionScreen(), self._on_new_session)

    def _on_new_session(self, result):
        if result is None:
            return
        if not result["name"] or not result["project"]:
            self.notify("Name and project are required", severity="error")
            return
        try:
            self.manager.new(**result)
            self._refresh()
            self.notify(f"Session '{result['name']}' created")
        except RuntimeError as exc:
            self.notify(str(exc), severity="error", timeout=10)

    def action_attach(self):
        name = self._selected_session()
        if name:
            self.exit((name, "attach"))

    def action_kill(self):
        name = self._selected_session()
        if name:
            self.push_screen(
                ConfirmScreen(f"Kill session '{name}'?"),
                lambda ok: self._do_kill(name) if ok else None,
            )

    def _do_kill(self, name: str):
        try:
            self.manager.kill(name)
            self._refresh()
            self.notify(f"Killed '{name}'")
        except RuntimeError as exc:
            self.notify(str(exc), severity="error")

    def action_model(self):
        name = self._selected_session()
        if not name:
            return
        current = "?"
        for s in self.manager.list():
            if s.name == name:
                current = s.model
                break
        self.push_screen(
            ModelScreen(current),
            lambda m: self._do_set_model(name, m) if m else None,
        )

    def _do_set_model(self, name: str, model: str):
        try:
            self.manager.set_model(name, model)
            self._refresh()
            self.notify(f"Restarted with model {model}")
        except RuntimeError as exc:
            self.notify(str(exc), severity="error", timeout=10)

    def action_rename(self):
        name = self._selected_session()
        if not name:
            return
        self.push_screen(
            RenameScreen(current=name),
            lambda new: self._do_rename(name, new) if new else None,
        )

    def _do_rename(self, old: str, new: str):
        try:
            self.manager.rename(old, new)
            self._refresh()
            self.notify(f"Renamed '{old}' → '{new}'")
        except RuntimeError as exc:
            self.notify(str(exc), severity="error")

    @work
    async def action_refresh(self):
        self._refresh()
        self.notify("Refreshed")

    def action_kill_all(self):
        sessions = self.manager.list()
        if not sessions:
            self.notify("No sessions to kill")
            return
        self.push_screen(
            ConfirmScreen(f"Kill all {len(sessions)} sessions?"),
            lambda ok: self._do_kill_all() if ok else None,
        )

    def _do_kill_all(self):
        for s in self.manager.list():
            try:
                self.manager.kill(s.name)
            except RuntimeError:
                pass
        self._refresh()
        self.notify("All sessions killed")
