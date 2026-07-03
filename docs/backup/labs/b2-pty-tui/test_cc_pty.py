"""Tests for cc-pty — manager, terminal_widget key mapping, and CLI."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# Patch the module-level constants BEFORE importing anything from cc_pty
_real_home = Path.home()

with tempfile.TemporaryDirectory() as TMP:
    # Override DATA_DIR etc.
    Path(TMP + "/.cc-pty").mkdir(parents=True, exist_ok=True)

    # We need to mock at module level before import
    pass

# ── Test Manager ──

def test_manager_crud():
    """Manager: add, get, list, remove, rename, set_model."""
    import tempfile, json
    from pathlib import Path

    # Create a temp data dir
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td) / ".cc-pty"
        sessions_file = data_dir / "sessions.json"

        # Patch the module constants
        with patch("cc_pty.manager.DATA_DIR", data_dir):
            with patch("cc_pty.manager.SESSIONS_FILE", sessions_file):
                from cc_pty.manager import Manager, Session

                mgr = Manager()

                # add
                s = mgr.add("test1", "/tmp/proj", "sonnet")
                assert s.name == "test1"
                assert s.project == "/tmp/proj"
                assert s.model == "sonnet"
                assert sessions_file.exists()

                # get
                s2 = mgr.get("test1")
                assert s2 is not None
                assert s2.name == "test1"

                # get missing
                assert mgr.get("nonexistent") is None

                # list
                mgr.add("test2", "/tmp/proj2", "haiku")
                lst = mgr.list()
                assert len(lst) == 2

                # rename
                s3 = mgr.rename("test1", "renamed")
                assert s3 is not None
                assert s3.name == "renamed"
                assert mgr.get("test1") is None
                assert mgr.get("renamed") is not None

                # set_model
                assert mgr.set_model("renamed", "opus")
                assert mgr.get("renamed").model == "opus"
                assert not mgr.set_model("nonexistent", "x")

                # remove
                mgr.remove("renamed")
                assert mgr.get("renamed") is None
                assert len(mgr.list()) == 1

                # reload from disk — verify persistence
                mgr2 = Manager()
                lst2 = mgr2.list()
                assert len(lst2) == 1
                assert lst2[0].name == "test2"


def test_manager_detect_model():
    """Manager.detect_model reads claude settings.json."""
    import tempfile, json
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        claude_dir = Path(td) / ".claude"
        claude_dir.mkdir()
        settings = claude_dir / "settings.json"
        settings.write_text(json.dumps({"model": "claude-sonnet-4-20250514"}))

        from cc_pty.manager import Manager
        assert Manager.detect_model(td) == "claude-sonnet-4-20250514"


def test_manager_detect_model_missing():
    """Manager.detect_model returns '?' when no settings.json."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        from cc_pty.manager import Manager
        assert Manager.detect_model(td) == "?"


def test_manager_apply_model():
    """Manager.apply_model calls claude-switch."""
    from cc_pty.manager import Manager
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        Manager.apply_model("/tmp/proj", "sonnet")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "claude-switch"
        assert args[1] == "sonnet"
        assert mock_run.call_args[1]["cwd"] == "/tmp/proj"


def test_manager_apply_model_failure():
    """Manager.apply_model raises RuntimeError on failure."""
    from cc_pty.manager import Manager
    import subprocess
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "error: unknown profile"
        try:
            Manager.apply_model("/tmp/proj", "bad-profile")
            assert False, "should have raised"
        except RuntimeError as e:
            assert "unknown profile" in str(e)


def test_manager_apply_model_not_found():
    """Manager.apply_model wraps FileNotFoundError."""
    from cc_pty.manager import Manager
    with patch("subprocess.run", side_effect=FileNotFoundError):
        try:
            Manager.apply_model("/tmp/proj", "m")
            assert False, "should have raised"
        except RuntimeError as e:
            assert "claude-switch not found" in str(e)


def test_manager_apply_model_timeout():
    """Manager.apply_model wraps TimeoutExpired."""
    from cc_pty.manager import Manager
    import subprocess
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=15)):
        try:
            Manager.apply_model("/tmp/proj", "m")
            assert False, "should have raised"
        except RuntimeError as e:
            assert "timed out" in str(e)


def test_new_session_duplicate_skips_apply_model():
    """Duplicate session names must fail before changing project model."""
    import asyncio
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td) / ".cc-pty"
        sessions_file = data_dir / "sessions.json"
        project_dir = Path(td) / "proj"
        project_dir.mkdir()
        with patch("cc_pty.manager.DATA_DIR", data_dir):
            with patch("cc_pty.manager.SESSIONS_FILE", sessions_file):
                from cc_pty.tui import PtyApp

                app = PtyApp()
                app.notify = MagicMock()
                app.manager.add("dup", str(project_dir), "sonnet")

                with patch(
                    "cc_pty.tui.Manager.apply_model",
                    side_effect=AssertionError("apply_model should not run"),
                ):
                    asyncio.run(
                        app._on_new_session(
                            {
                                "name": "dup",
                                "project": str(project_dir),
                                "model": "opus",
                            }
                        )
                    )

                app.notify.assert_called()
                assert "already exists" in str(app.notify.call_args.args[0])


def test_manager_add_duplicate():
    """Manager.add raises ValueError on duplicate name."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        with patch("cc_pty.manager.DATA_DIR", Path(td) / ".cc-pty"):
            with patch("cc_pty.manager.SESSIONS_FILE", Path(td) / ".cc-pty" / "sessions.json"):
                from cc_pty.manager import Manager
                mgr = Manager()
                mgr.add("dup", "/tmp/p1")
                try:
                    mgr.add("dup", "/tmp/p2")
                    assert False, "should have raised"
                except ValueError as e:
                    assert "already exists" in str(e)


def test_manager_rename_collision():
    """Manager.rename raises ValueError on empty name or collision."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        with patch("cc_pty.manager.DATA_DIR", Path(td) / ".cc-pty"):
            with patch("cc_pty.manager.SESSIONS_FILE", Path(td) / ".cc-pty" / "sessions.json"):
                from cc_pty.manager import Manager
                mgr = Manager()
                mgr.add("a", "/tmp/p1")
                mgr.add("b", "/tmp/p2")

                # empty name
                try:
                    mgr.rename("a", "  ")
                    assert False, "should have raised"
                except ValueError as e:
                    assert "cannot be empty" in str(e)

                # collision
                try:
                    mgr.rename("a", "b")
                    assert False, "should have raised"
                except ValueError as e:
                    assert "already exists" in str(e)


# ── Test TerminalWidget statics ──

def test_key_to_bytes_ctrl():
    """_key_to_bytes maps ctrl+letter to correct byte."""
    from cc_pty.terminal_widget import TerminalWidget
    from textual.events import Key

    # ctrl+a → 1
    event = MagicMock(spec=Key)
    event.key = "ctrl+a"
    event.character = None
    assert TerminalWidget._key_to_bytes(event) == b"\x01"

    # ctrl+d → 4
    event.key = "ctrl+d"
    assert TerminalWidget._key_to_bytes(event) == b"\x04"

    # ctrl+z → 26
    event.key = "ctrl+z"
    assert TerminalWidget._key_to_bytes(event) == b"\x1a"


def test_key_to_bytes_special():
    """_key_to_bytes maps named keys to escape sequences."""
    from cc_pty.terminal_widget import TerminalWidget
    from textual.events import Key

    cases = {
        "enter": b"\r",
        "backspace": b"\x7f",
        "tab": b"\t",
        "escape": b"\x1b",
        "up": b"\x1b[A",
        "down": b"\x1b[B",
        "right": b"\x1b[C",
        "left": b"\x1b[D",
        "home": b"\x1b[H",
        "end": b"\x1b[F",
        "delete": b"\x1b[3~",
    }
    for key, expected in cases.items():
        event = MagicMock(spec=Key)
        event.key = key
        event.character = None
        result = TerminalWidget._key_to_bytes(event)
        assert result == expected, f"{key}: expected {expected!r}, got {result!r}"


def test_key_to_bytes_fkeys():
    """_key_to_bytes maps F-keys."""
    from cc_pty.terminal_widget import TerminalWidget
    from textual.events import Key

    fkey_cases = {
        "f1": b"\x1bOP",
        "f2": b"\x1bOQ",
        "f3": b"\x1bOR",
        "f4": b"\x1bOS",
        "f5": b"\x1b[15~",
        "f6": b"\x1b[17~",
        "f7": b"\x1b[18~",
        "f8": b"\x1b[19~",
        "f9": b"\x1b[20~",
        "f10": b"\x1b[21~",
        "f11": b"\x1b[23~",
        "f12": b"\x1b[24~",
    }
    for key, expected in fkey_cases.items():
        event = MagicMock(spec=Key)
        event.key = key
        event.character = None
        result = TerminalWidget._key_to_bytes(event)
        assert result == expected, f"{key}: expected {expected!r}, got {result!r}"


def test_key_to_bytes_printable():
    """_key_to_bytes passes through printable characters."""
    from cc_pty.terminal_widget import TerminalWidget
    from textual.events import Key

    event = MagicMock(spec=Key)
    event.key = "a"
    event.character = "a"
    assert TerminalWidget._key_to_bytes(event) == b"a"

    # Unicode char
    event.key = "你"
    event.character = "你"
    assert TerminalWidget._key_to_bytes(event) == "你".encode("utf-8")


def test_key_to_bytes_unknown():
    """_key_to_bytes returns empty bytes for unmapped keys."""
    from cc_pty.terminal_widget import TerminalWidget
    from textual.events import Key

    event = MagicMock(spec=Key)
    event.key = "unknown_key_xyz"
    event.character = None
    assert TerminalWidget._key_to_bytes(event) == b""


def test_terminal_widget_focusable():
    """TerminalWidget must be keyboard-focusable for PTY input to work."""
    from cc_pty.terminal_widget import TerminalWidget

    assert TerminalWidget.can_focus is True
    assert TerminalWidget.focus_on_click is True


def test_ensure_terminal_recreates_dead_widget():
    """Dead PTY widgets should be removed and recreated on selection."""
    import asyncio
    import tempfile

    class DeadTerm:
        _alive = False

        def __init__(self):
            self.removed = False

        async def remove(self):
            self.removed = True

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td) / ".cc-pty"
        sessions_file = data_dir / "sessions.json"
        with patch("cc_pty.manager.DATA_DIR", data_dir):
            with patch("cc_pty.manager.SESSIONS_FILE", sessions_file):
                from cc_pty.tui import PtyApp

                app = PtyApp()
                dead = DeadTerm()
                app._terminals["dead"] = dead
                app._create_terminal = AsyncMock(return_value=True)

                result = asyncio.run(app._ensure_terminal("dead"))

                assert result is True
                assert app._create_terminal.await_count == 1
                assert dead.removed is True
                assert "dead" not in app._terminals


def test_resolve_color_ansi():
    """_resolve_color maps ANSI 0-15 to hex."""
    from cc_pty.terminal_widget import TerminalWidget, ANSI_COLORS

    assert TerminalWidget._resolve_color(0) == ANSI_COLORS[0]
    assert TerminalWidget._resolve_color(7) == ANSI_COLORS[7]
    assert TerminalWidget._resolve_color(15) == ANSI_COLORS[15]


def test_resolve_color_256_unsupported():
    """_resolve_color returns None for 256-color index."""
    from cc_pty.terminal_widget import TerminalWidget
    assert TerminalWidget._resolve_color(42) is None
    assert TerminalWidget._resolve_color(255) is None


def test_resolve_color_truecolor():
    """_resolve_color handles true-color hex strings."""
    from cc_pty.terminal_widget import TerminalWidget
    assert TerminalWidget._resolve_color("#ff0000") == "#ff0000"
    assert TerminalWidget._resolve_color("#00ff00") == "#00ff00"
    assert TerminalWidget._resolve_color("#123abc") == "#123abc"


def test_resolve_color_invalid():
    """_resolve_color returns None for unexpected types."""
    from cc_pty.terminal_widget import TerminalWidget
    assert TerminalWidget._resolve_color(None) is None
    assert TerminalWidget._resolve_color("default") is None


def test_control_map_coverage():
    """CONTROL_MAP covers all ctrl+a through ctrl+z plus special keys."""
    from cc_pty.terminal_widget import CONTROL_MAP
    for ch in "abcdefghijklmnopqrstuvwxyz":
        key = f"ctrl+{ch}"
        assert key in CONTROL_MAP, f"missing {key}"
        assert CONTROL_MAP[key] == ord(ch) - ord("a") + 1

    specials = ["ctrl+@", "ctrl+[", "ctrl+\\", "ctrl+]", "ctrl+^", "ctrl+_", "ctrl+backspace"]
    for s in specials:
        assert s in CONTROL_MAP, f"missing {s}"


def test_special_map_completeness():
    """SPECIAL_MAP has all critical terminal keys."""
    from cc_pty.terminal_widget import SPECIAL_MAP
    required = ["enter", "backspace", "tab", "escape", "up", "down",
                "right", "left", "home", "end", "delete"]
    for k in required:
        assert k in SPECIAL_MAP, f"missing {k}"


def test_app_bindings_not_priority():
    """Global app shortcuts must not preempt terminal input."""
    from cc_pty.tui import PtyApp

    assert all(not binding.priority for binding in PtyApp.BINDINGS)


# ── Test CLI ──

def test_cli_default_tui():
    """CLI defaults to tui command."""
    from cc_pty.cli import cli
    with patch("cc_pty.cli.cmd_tui") as mock_tui:
        with patch("sys.argv", ["cc-pty"]):
            # argparse will use sys.argv, so we override
            with patch("argparse.ArgumentParser.parse_args") as mock_parse:
                mock_parse.return_value = MagicMock(command="tui")
                cli()
                mock_tui.assert_called_once()


def test_cli_list():
    """CLI 'list' calls cmd_list."""
    from cc_pty.cli import cli
    with patch("cc_pty.cli.cmd_list") as mock_list:
        with patch("argparse.ArgumentParser.parse_args") as mock_parse:
            mock_parse.return_value = MagicMock(command="list")
            cli()
            mock_list.assert_called_once()


# ── Run ──

if __name__ == "__main__":
    import traceback

    tests = [
        ("test_manager_crud", test_manager_crud),
        ("test_manager_detect_model", test_manager_detect_model),
        ("test_manager_detect_model_missing", test_manager_detect_model_missing),
        ("test_manager_apply_model", test_manager_apply_model),
        ("test_manager_apply_model_failure", test_manager_apply_model_failure),
        ("test_manager_apply_model_not_found", test_manager_apply_model_not_found),
        ("test_manager_apply_model_timeout", test_manager_apply_model_timeout),
        ("test_manager_add_duplicate", test_manager_add_duplicate),
        ("test_manager_rename_collision", test_manager_rename_collision),
        ("test_key_to_bytes_ctrl", test_key_to_bytes_ctrl),
        ("test_key_to_bytes_special", test_key_to_bytes_special),
        ("test_key_to_bytes_fkeys", test_key_to_bytes_fkeys),
        ("test_key_to_bytes_printable", test_key_to_bytes_printable),
        ("test_key_to_bytes_unknown", test_key_to_bytes_unknown),
        ("test_terminal_widget_focusable", test_terminal_widget_focusable),
        ("test_resolve_color_ansi", test_resolve_color_ansi),
        ("test_resolve_color_256_unsupported", test_resolve_color_256_unsupported),
        ("test_resolve_color_truecolor", test_resolve_color_truecolor),
        ("test_resolve_color_invalid", test_resolve_color_invalid),
        ("test_control_map_coverage", test_control_map_coverage),
        ("test_special_map_completeness", test_special_map_completeness),
        ("test_app_bindings_not_priority", test_app_bindings_not_priority),
        ("test_cli_default_tui", test_cli_default_tui),
        ("test_cli_list", test_cli_list),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"  PASS  {name}")
        except Exception:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc()

    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    if failed:
        sys.exit(1)
