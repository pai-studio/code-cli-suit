"""TUI for cc-pty -- sidebar + embedded terminal emulator."""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from .manager import Manager, Session
from .terminal_widget import TerminalWidget


# ===================================================================
# Modal screens
# ===================================================================


class NewSessionScreen(ModalScreen):
    """Modal: gather name / project / model for a new session."""

    def compose(self):
        with Vertical(id="dialog"):
            yield Label("New Claude Code Session", classes="title")
            yield Input(placeholder="Session name", id="name")
            yield Input(
                placeholder="Project path (e.g. . or ~/projects/app)",
                id="project",
                value=".",
            )
            yield Input(
                placeholder="Model (optional, e.g. sonnet, deepseek-pro)",
                id="model",
            )
            with Horizontal(id="buttons"):
                yield Button("Create", variant="primary", id="create")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
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

    def on_mount(self) -> None:
        self.query_one("#name", Input).focus()


class RenameScreen(ModalScreen):
    """Modal: rename a session or change its model."""

    def __init__(self, current_name: str) -> None:
        super().__init__()
        self._current = current_name

    def compose(self):
        with Vertical(id="dialog"):
            yield Label("Rename Session", classes="title")
            yield Label(f"Current: {self._current}")
            yield Input(placeholder="New name", id="name", value=self._current)
            yield Input(
                placeholder="Model (changes take effect on restart)",
                id="model",
            )
            with Horizontal(id="buttons"):
                yield Button("Apply", variant="primary", id="apply")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "apply":
            self.dismiss(
                {
                    "name": self.query_one("#name", Input).value.strip(),
                    "model": self.query_one("#model", Input).value.strip() or None,
                }
            )
        else:
            self.dismiss(None)

    def on_mount(self) -> None:
        self.query_one("#name", Input).focus()


class ConfirmKill(ModalScreen):
    """Confirm destroying a session."""

    def __init__(self, session_name: str) -> None:
        super().__init__()
        self._name = session_name

    def compose(self):
        with Vertical(id="dialog"):
            yield Label(f"Kill session '{self._name}'?", classes="title")
            yield Label("All unsaved work will be lost.")
            with Horizontal(id="buttons"):
                yield Button("Kill", variant="error", id="kill")
                yield Button("Cancel", variant="primary", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "kill")


# ===================================================================
# Sidebar item
# ===================================================================


class SessionListItem(ListItem):
    """A single row in the sidebar session list."""

    def __init__(self, session: Session, active: bool = False) -> None:
        super().__init__()
        self.session_name = session.name
        self._project = Path(session.project).name
        self._model = session.model
        self._active = active

    def compose(self):
        indicator = "●" if self._active else "○"
        yield Label(f"{indicator} {self.session_name}", classes="sess-name")
        yield Label(f"  {self._project}", classes="sess-detail")
        yield Label(f"  {self._model}", classes="sess-detail")


# ===================================================================
# Main app
# ===================================================================


class PtyApp(App):
    """Multi-session Claude Code manager with embedded PTY terminals."""

    BINDINGS = [
        Binding("ctrl+n", "new_session", "New"),
        Binding("ctrl+w", "kill_session", "Kill"),
        Binding("ctrl+r", "rename_session", "Rename"),
        Binding("ctrl+space", "focus_sidebar", "Sidebar"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("f5", "refresh_sidebar", "Refresh"),
    ]

    CSS = """
    Screen { layout: vertical; }

    #body { height: 1fr; }

    /* ---- Sidebar ---- */
    #sidebar {
        width: 28;
        dock: left;
        border: solid $primary;
        height: 100%;
    }
    #sidebar-title {
        padding: 0 1;
        background: $primary;
        color: $text;
        text-style: bold;
    }
    #session-list { height: 1fr; }
    #session-list:focus { border: none; }

    SessionListItem {
        padding: 0 1;
        height: auto;
    }
    SessionListItem:hover {
        background: $boost;
    }
    SessionListItem > .sess-name {
        text-style: bold;
    }
    SessionListItem > .sess-detail {
        color: $text-muted;
    }

    #sidebar-actions {
        height: auto;
        border-top: solid $primary;
        padding: 0 1;
        color: $text-muted;
    }

    /* ---- Main area ---- */
    #main-area {
        height: 100%;
    }

    #placeholder {
        content-align: center middle;
        color: $text-muted;
        height: 100%;
    }

    /* ---- Modal dialogs ---- */
    #dialog {
        padding: 1 2;
        width: 54;
        min-height: 10;
        border: thick $primary;
        background: $surface;
    }
    #buttons { height: 3; align: center middle; }
    .title { text-style: bold; padding-bottom: 1; }
    Input { margin-bottom: 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.manager = Manager()
        self._terminals: dict[str, TerminalWidget] = {}
        self._active: str | None = None

    def compose(self):
        yield Header(show_clock=False)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Label("Sessions", id="sidebar-title")
                yield ListView(id="session-list")
                with Vertical(id="sidebar-actions"):
                    yield Label("[Ctrl+N] New  [Ctrl+W] Kill")
                    yield Label("[Ctrl+R] Rename  [Ctrl+Space] Sidebar")
            with Vertical(id="main-area"):
                yield Static(
                    "No session selected.\nPress Ctrl+N to create one.",
                    id="placeholder",
                )
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_sidebar()

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def _refresh_sidebar(self) -> None:
        lv = self.query_one("#session-list", ListView)
        lv.clear()
        sessions = self.manager.list()
        for s in sessions:
            item = SessionListItem(s, active=(s.name == self._active))
            lv.append(item)
        # Keep selection aligned
        if lv.children and self._active:
            for i, child in enumerate(lv.children):
                if getattr(child, "session_name", None) == self._active:
                    lv.index = i
                    break

    # ------------------------------------------------------------------
    # Session switching
    # ------------------------------------------------------------------

    def _show_session(self, name: str) -> None:
        placeholder = self.query_one("#placeholder", Static)
        placeholder.display = True

        for tname, term in self._terminals.items():
            visible = tname == name
            term.display = visible
            if visible:
                placeholder.display = False
                if not term.has_focus:
                    term.focus()

        self._active = name
        self._refresh_sidebar()

    async def _create_terminal(self, name: str) -> bool:
        """Create a new TerminalWidget for *name*, spawns a fresh PTY."""
        session = self.manager.get(name)
        if session is None:
            return False

        term = TerminalWidget("claude", cwd=session.project, session_name=name)
        term.display = False
        self._terminals[name] = term
        await self.query_one("#main-area", Vertical).mount(term)
        return True

    async def _ensure_terminal(self, name: str) -> bool:
        """Get or create a TerminalWidget for *name*."""
        term = self._terminals.get(name)
        if term is not None and getattr(term, "_alive", False):
            return True
        if term is not None:
            self._terminals.pop(name, None)
            try:
                await term.remove()
            except Exception:
                pass
        return await self._create_terminal(name)

    async def _restart_terminal(self, name: str) -> bool:
        """Kill and recreate the terminal for *name* (e.g. after model change)."""
        if name in self._terminals:
            old = self._terminals.pop(name)
            await old.remove()
        return await self._create_terminal(name)

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        name = getattr(item, "session_name", None)
        if name is not None:
            ok = await self._ensure_terminal(name)
            if ok:
                self._show_session(name)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def action_new_session(self) -> None:
        self.push_screen(NewSessionScreen(), self._on_new_session)

    async def _on_new_session(self, result) -> None:
        if result is None:
            return
        name = result["name"]
        project = result["project"]
        model = result["model"]

        if not name or not project:
            self.notify("Name and project are required", severity="error")
            return

        project_path = Path(project).expanduser().resolve()
        if not project_path.is_dir():
            self.notify(f"Directory not found: {project_path}", severity="error")
            return

        try:
            if self.manager.get(name):
                self.notify(f"Session '{name}' already exists", severity="error")
                return

            if model:
                Manager.apply_model(str(project_path), model)
                detected = model
            else:
                detected = Manager.detect_model(str(project_path))

            self.manager.add(name, str(project_path), detected)

            ok = await self._ensure_terminal(name)
            if ok:
                self._show_session(name)
                self.notify(f"Session '{name}' created")
        except (RuntimeError, ValueError) as exc:
            self.notify(str(exc), severity="error", timeout=10)

    def action_kill_session(self) -> None:
        if self._active is None:
            self.notify("No active session", severity="warning")
            return
        self.push_screen(
            ConfirmKill(self._active),
            self._on_kill_confirm,
        )

    async def _on_kill_confirm(self, confirmed: bool) -> None:
        if not confirmed or self._active is None:
            return
        name = self._active

        if name in self._terminals:
            term = self._terminals.pop(name)
            await term.remove()

        self.manager.remove(name)

        remaining = self.manager.list()
        if remaining:
            self._active = remaining[0].name
            await self._ensure_terminal(self._active)
            self._show_session(self._active)
        else:
            self._active = None
            placeholder = self.query_one("#placeholder", Static)
            placeholder.display = True

        self._refresh_sidebar()
        self.notify(f"Session '{name}' killed")

    def action_rename_session(self) -> None:
        if self._active is None:
            self.notify("No active session", severity="warning")
            return
        self.push_screen(
            RenameScreen(self._active),
            self._on_rename,
        )

    async def _on_rename(self, result) -> None:
        if result is None or self._active is None:
            return
        new_name = result["name"]
        new_model = result["model"]
        old_name = self._active

        if not new_name:
            self.notify("Session name cannot be empty", severity="error")
            return

        if new_name != old_name:
            try:
                self.manager.rename(old_name, new_name)
            except ValueError as exc:
                self.notify(str(exc), severity="error")
                return
            if old_name in self._terminals:
                self._terminals[new_name] = self._terminals.pop(old_name)
                self._terminals[new_name].session_name = new_name
            self._active = new_name

        if new_model:
            try:
                session = self.manager.get(self._active)
                if session:
                    Manager.apply_model(session.project, new_model)
                    self.manager.set_model(self._active, new_model)
                    # Restart the terminal so the running Claude picks up the new model
                    if self._active in self._terminals:
                        await self._restart_terminal(self._active)
                        self._show_session(self._active)
                        self.notify(
                            f"Model changed to {new_model}, terminal restarted"
                        )
                    else:
                        self.notify(f"Model set to {new_model} (next launch)")
            except (RuntimeError, ValueError) as exc:
                self.notify(str(exc), severity="error", timeout=10)

        self._refresh_sidebar()

    def action_focus_sidebar(self) -> None:
        lv = self.query_one("#session-list", ListView)
        lv.focus()

    async def action_refresh_sidebar(self) -> None:
        self._refresh_sidebar()
        self.notify("Refreshed")
