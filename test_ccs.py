"""Tests for the ccs command helpers."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claude_switch.ccs import (
    HELP,
    HELP_ZH,
    CcsOptions,
    _launcher_command,
    main,
    _parse_cc_options,
    _parse_monitor_args,
    _parse_sidebar_args,
    _run_tui,
    _session_picker_marker,
    _tail_nonempty,
)
from claude_switch.models import add_model_mapping, list_providers, resolve_model_spec
from claude_switch.protocol import CcsClient
from claude_switch.session import CodeSession, SessionManager
from claude_switch.store import CcsPaths, SessionStore
from claude_switch.tui import CcsTuiApp, DEFAULT_TUI_MODEL, parse_new_session_request
from claude_switch.adapters import get_adapter
from claude_switch.daemon import _screen_lines
from claude_switch.workbench import TerminalPane, _session_signature, format_terminal_lines


class CcsParseTests(unittest.TestCase):
    def test_plain_claude_help_is_passthrough(self):
        opts, passthrough, managed = _parse_cc_options(["--help"])

        self.assertFalse(managed)
        self.assertEqual(passthrough, ["--help"])
        self.assertIsNone(opts.model)

    def test_cc_model_preserves_claude_args_order(self):
        opts, passthrough, managed = _parse_cc_options(
            ["--cc-model", "deepseek-flash", "--permission-mode", "acceptEdits"]
        )

        self.assertTrue(managed)
        self.assertEqual(opts.model, "deepseek-flash")
        self.assertEqual(passthrough, ["--permission-mode", "acceptEdits"])

    def test_unknown_cc_option_exits(self):
        with self.assertRaises(SystemExit):
            _parse_cc_options(["--cc-nope"])

    def test_help_mentions_launcher_and_tmux(self):
        self.assertIn("ccs tui", HELP)
        self.assertIn("ccs tui", HELP_ZH)
        self.assertIn("ccs claude --cc-model ds/flash", HELP)
        self.assertIn("ccs tmux", HELP)
        self.assertNotIn("ccs panel", HELP)
        self.assertNotIn("ccs workbench", HELP)

    def test_no_args_prints_help_instead_of_opening_panel(self):
        with patch("builtins.print") as print_:
            main([])

        print_.assert_called_once_with(HELP)

    def test_tui_rejects_extra_args(self):
        with self.assertRaises(SystemExit):
            _run_tui(["--bad"])

    def test_sidebar_args_support_focus_back_pane(self):
        current, main_pane = _parse_sidebar_args(["--current", "api", "--main-pane", "%2"])

        self.assertEqual(current, "api")
        self.assertEqual(main_pane, "%2")

    def test_session_picker_marker_shows_current_and_cursor(self):
        self.assertEqual(_session_picker_marker(is_selected=True, is_current=True), ">*")
        self.assertEqual(_session_picker_marker(is_selected=True, is_current=False), "> ")
        self.assertEqual(_session_picker_marker(is_selected=False, is_current=True), " *")
        self.assertEqual(_session_picker_marker(is_selected=False, is_current=False), "  ")

    def test_monitor_args_are_low_burden(self):
        names, lines, interval, once = _parse_monitor_args(
            ["api", "ui", "--lines", "80", "--interval", "1.5", "--once"]
        )

        self.assertEqual(names, ["api", "ui"])
        self.assertEqual(lines, 80)
        self.assertEqual(interval, 1.5)
        self.assertTrue(once)

    def test_tail_nonempty_trims_blank_tail(self):
        self.assertEqual(_tail_nonempty("a\nb\n\n", 1), "b")

    def test_launcher_dry_run_does_not_create_state(self):
        with tempfile.TemporaryDirectory() as td:
            opts = CcsOptions(model="default", name="demo", project=".")
            with patch.dict(os.environ, {"CCS_LAUNCHER_HOME": str(Path(td) / "launcher")}, clear=False):
                command, env = _launcher_command("claude", opts, [], create=False)

            self.assertEqual(command, ["claude", "--name", "demo"])
            self.assertNotIn("CLAUDE_CONFIG_DIR", env)
            self.assertEqual(env, {})
            self.assertFalse((Path(td) / "launcher").exists())


class SessionHelperTests(unittest.TestCase):
    def test_claude_argv_adds_settings_and_name(self):
        argv = SessionManager._claude_argv(
            "api-review",
            Path("/tmp/settings.json"),
            ["--permission-mode", "acceptEdits"],
        )

        self.assertEqual(
            argv,
            [
                "claude",
                "--settings",
                "/tmp/settings.json",
                "--name",
                "api-review",
                "--permission-mode",
                "acceptEdits",
            ],
        )

    def test_claude_argv_respects_existing_name(self):
        argv = SessionManager._claude_argv(
            "api-review",
            None,
            ["--name", "custom"],
        )

        self.assertEqual(argv, ["claude", "--name", "custom"])

    def test_shell_command_does_not_isolate_config_dir(self):
        command = SessionManager._shell_command(
            ["claude", "--name", "review"],
        )

        self.assertNotIn("CLAUDE_CONFIG_DIR", command)
        self.assertIn("exec claude --name review", command)

    def test_write_claude_settings_uses_0600_permissions(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "session.settings.json"
            profiles = {"dp": {"model": "deepseek-v4-flash", "provider": "deepseek"}}
            with patch("claude_switch.models.load_profiles", return_value=profiles), patch.dict(
                os.environ, {"DEEPSEEK_API_KEY": "sk-test"}, clear=False
            ):
                SessionManager._write_claude_settings("dp", path)

            data = json.loads(path.read_text())
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(data["model"], "deepseek-v4-flash")
            self.assertEqual(mode, 0o600)

    def test_settings_path_uses_xdg_state_home(self):
        with tempfile.TemporaryDirectory() as td:
            old = os.environ.get("XDG_STATE_HOME")
            os.environ["XDG_STATE_HOME"] = td
            try:
                path = SessionManager._settings_path("api-review", "claude")
            finally:
                if old is None:
                    os.environ.pop("XDG_STATE_HOME", None)
                else:
                    os.environ["XDG_STATE_HOME"] = old

        self.assertIn("ccs/sessions", str(path))
        self.assertTrue(path.name.endswith(".claude.settings.json"))

    def test_config_dir_path_uses_xdg_state_home(self):
        with tempfile.TemporaryDirectory() as td:
            old = os.environ.get("XDG_STATE_HOME")
            os.environ["XDG_STATE_HOME"] = td
            try:
                path = SessionManager._config_dir_path("api-review", "claude")
            finally:
                if old is None:
                    os.environ.pop("XDG_STATE_HOME", None)
                else:
                    os.environ["XDG_STATE_HOME"] = old

        self.assertIn("ccs/sessions", str(path))
        self.assertTrue(path.name.endswith(".claude.config"))

    def test_view_session_name_is_per_code_session(self):
        code = SessionManager._view_session_name("code")
        review = SessionManager._view_session_name("review")

        self.assertTrue(code.startswith("ccs-view-code-"))
        self.assertTrue(review.startswith("ccs-view-review-"))
        self.assertNotEqual(code, review)

    def test_attach_uses_per_session_grouped_view(self):
        calls = []
        manager = object.__new__(SessionManager)
        session = CodeSession(
            name="review",
            tool="claude",
            model="an/sonnet",
            project="/tmp/project",
            index=2,
            pid=123,
            running=True,
        )

        def fake_tmux(*args):
            calls.append(args)
            if args[:2] == ("show-option", "-wqv"):
                return "%9"
            return ""

        view_session = SessionManager._view_session_name("review")

        def fake_raw(*args):
            exists = any(call == ("new-session", "-d", "-t", "ccs", "-s", view_session) for call in calls)
            code = 0 if args == ("has-session", "-t", view_session) and exists else 1
            return type("R", (), {"returncode": code, "stdout": "", "stderr": ""})()

        manager.list = lambda: [session]
        manager._tmux = fake_tmux
        manager._raw = fake_raw
        manager._sync_sidebar = lambda name: calls.append(("sync-sidebar", name))

        with patch.dict(os.environ, {}, clear=True), patch("subprocess.run") as run:
            manager.attach("review")

        joined = [" ".join(args) for args in calls]
        self.assertTrue(any(f"new-session -d -t ccs -s {view_session}" in call for call in joined))
        self.assertTrue(any(f"select-window -t {view_session}:2" in call for call in joined))
        run.assert_called_once_with(["tmux", "attach-session", "-t", view_session])

    def test_sidebar_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(SessionManager._sidebar_enabled())

    def test_sidebar_can_be_enabled_for_legacy_users(self):
        with patch.dict(os.environ, {SessionManager.SIDEBAR_ENV: "1"}, clear=True):
            self.assertTrue(SessionManager._sidebar_enabled())

    def test_tmux_mouse_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(SessionManager._mouse_enabled())

    def test_tmux_mouse_can_be_enabled_for_scrolling(self):
        with patch.dict(os.environ, {SessionManager.MOUSE_ENV: "1"}, clear=True):
            self.assertTrue(SessionManager._mouse_enabled())

    def test_ccs_key_bindings_use_ccs_select_commands(self):
        calls = []

        manager = object.__new__(SessionManager)

        def fake_tmux(*args):
            calls.append(args)
            return ""

        manager._tmux = fake_tmux
        manager._ensure_key_bindings()

        joined = [" ".join(args) for args in calls]
        self.assertTrue(any("ccs select next" in call for call in joined))
        self.assertTrue(any("ccs select prev" in call for call in joined))
        self.assertTrue(any("ccs focus" in call for call in joined))
        self.assertTrue(any("ccs-view-" in call for call in joined))
        self.assertFalse(any("previous-window" == args[-1] for args in calls if args[:2] == ("bind-key", "-n")))
        self.assertFalse(any("next-window" == args[-1] for args in calls if args[:2] == ("bind-key", "-n")))

    def test_status_bar_contains_low_burden_hints(self):
        calls = []
        manager = object.__new__(SessionManager)

        def fake_tmux(*args):
            calls.append(args)
            return ""

        manager._tmux = fake_tmux
        manager._ensure_status_bar(SessionManager.TMUX_SESSION)

        joined = [" ".join(args) for args in calls]
        self.assertTrue(any("Fn-Up/Fn-Down scroll" in call for call in joined))
        self.assertTrue(any("C-b i focus" in call for call in joined))
        self.assertTrue(any("j/k u/d g/G" in call for call in joined))

    def test_copy_mode_supports_scroll_without_page_keys(self):
        calls = []
        manager = object.__new__(SessionManager)

        def fake_tmux(*args):
            calls.append(args)
            return ""

        manager._tmux = fake_tmux
        manager._ensure_key_bindings()

        joined = [" ".join(args) for args in calls]
        self.assertTrue(any("PPage" in call for call in joined))
        self.assertTrue(any("NPage" in call for call in joined))
        self.assertTrue(any("page-up" in call for call in joined))
        self.assertTrue(any("page-down" in call for call in joined))
        self.assertTrue(any("halfpage-up" in call for call in joined))
        self.assertTrue(any("halfpage-down" in call for call in joined))
        self.assertTrue(any("history-top" in call for call in joined))
        self.assertTrue(any("history-bottom" in call for call in joined))


class ModelRegistryTests(unittest.TestCase):
    def test_anthropic_alias_is_an(self):
        providers = {provider.id: provider for provider in list_providers()}

        self.assertIn("an", providers["anthropic"].aliases)
        self.assertNotIn("a", providers["anthropic"].aliases)

    def test_resolves_deepseek_provider_model(self):
        resolved = resolve_model_spec("ds/flash")

        self.assertEqual(resolved.provider, "deepseek")
        self.assertEqual(resolved.actual_model, "deepseek-v4-flash")
        self.assertEqual(resolved.canonical, "ds/flash")

    def test_resolves_anthropic_provider_model(self):
        resolved = resolve_model_spec("an/sonnet")

        self.assertEqual(resolved.provider, "anthropic")
        self.assertEqual(resolved.actual_model, "sonnet")

    def test_resolves_openai_model_for_codex_adapter(self):
        resolved = resolve_model_spec("openai/gpt-5")

        self.assertEqual(resolved.provider, "openai")
        self.assertEqual(resolved.actual_model, "gpt-5")

    def test_resolves_openrouter_short_model_to_actual_author_model(self):
        resolved = resolve_model_spec("or/kimi-k2.6")

        self.assertEqual(resolved.provider, "openrouter")
        self.assertEqual(resolved.actual_model, "moonshotai/kimi-k2.6")

    def test_resolves_legacy_openrouter_profile(self):
        resolved = resolve_model_spec("openrouter/kimi-k2.6")

        self.assertEqual(resolved.canonical, "or/kimi-k2.6")
        self.assertEqual(resolved.actual_model, "moonshotai/kimi-k2.6")

    def test_custom_openrouter_mapping_does_not_store_key(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "models.json"
            with patch.dict(os.environ, {"CCS_MODELS_FILE": str(path)}, clear=False):
                add_model_mapping("or/qwen3-coder", "qwen/qwen3-coder")
                resolved = resolve_model_spec("or/qwen3-coder")

            data = json.loads(path.read_text())
            self.assertEqual(resolved.actual_model, "qwen/qwen3-coder")
            self.assertEqual(data, {"models": {"or/qwen3-coder": "qwen/qwen3-coder"}})


class DaemonStoreTests(unittest.TestCase):
    def test_store_creates_auto_name_without_secret_env(self):
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(CcsPaths(Path(td)))
            record = store.make_record(
                tool="claude",
                model="ds/flash",
                project=".",
                argv=["--permission-mode", "acceptEdits"],
            )
            store.upsert(record)
            loaded = store.get(record.name)

        self.assertIsNotNone(loaded)
        self.assertTrue(record.name.startswith("claude-ds-flash-"))
        self.assertEqual(record.env, {})
        self.assertEqual(record.argv, ["--permission-mode", "acceptEdits"])

    def test_client_ensure_daemon_returns_when_ping_succeeds(self):
        client = CcsClient(CcsPaths(Path("/tmp/ccs-test")))
        with patch.object(client, "call", return_value={"pid": 1}) as call:
            client.ensure_daemon()

        call.assert_called_once_with("daemon.ping", {})

    def test_claude_adapter_does_not_isolate_config_dir(self):
        with tempfile.TemporaryDirectory() as td:
            paths = CcsPaths(Path(td))
            store = SessionStore(paths)
            record = store.make_record(
                tool="claude",
                model="default",
                project=".",
                argv=[],
                name="review",
            )
            prepared = get_adapter("claude").prepare(record, paths)

        self.assertEqual(prepared.command, ["claude", "--name", "review"])
        self.assertNotIn("CLAUDE_CONFIG_DIR", prepared.env)

    def test_codex_adapter_accepts_openai_model(self):
        with tempfile.TemporaryDirectory() as td:
            paths = CcsPaths(Path(td))
            store = SessionStore(paths)
            record = store.make_record(
                tool="codex",
                model="openai/gpt-5",
                project=".",
                argv=["--help"],
                name="codex-review",
            )
            prepared = get_adapter("codex").prepare(record, paths)

        self.assertEqual(prepared.command, ["codex", "--model", "gpt-5", "--help"])

    def test_pyte_screen_lines_show_current_screen_without_repaint_log(self):
        import pyte

        screen = pyte.HistoryScreen(10, 3, history=5)
        stream = pyte.Stream(screen)
        stream.feed("\n".join(str(i) for i in range(10)))

        self.assertEqual(_screen_lines(screen, 4), ["      6", "       7", "        8", "         9"])

    def test_panel_formats_terminal_lines_to_fit_width(self):
        lines = ["short", "abcdef", "line\twith\ttabs"]

        self.assertEqual(
            format_terminal_lines(lines, width=5, height=3),
            ["short", "abcd…", "line…"],
        )

    def test_terminal_pane_focus_on_click_is_callable_for_textual(self):
        pane = TerminalPane(app_ref=None)

        self.assertTrue(callable(pane.focus_on_click))
        self.assertTrue(pane.focus_on_click())

    def test_session_signature_ignores_transient_running_bool(self):
        sessions = [
            {"id": "1", "name": "api", "tool": "claude", "model": "ds/flash", "status": "running", "running": True}
        ]
        same = [
            {"id": "1", "name": "api", "tool": "claude", "model": "ds/flash", "status": "running", "running": False}
        ]

        self.assertEqual(_session_signature(sessions), _session_signature(same))


class TuiHelperTests(unittest.TestCase):
    def test_new_session_request_allows_empty_name_and_defaults(self):
        request = parse_new_session_request(name="", project="", model="", args="")

        self.assertIsNone(request.name)
        self.assertEqual(request.project, ".")
        self.assertEqual(request.model, DEFAULT_TUI_MODEL)
        self.assertEqual(request.passthrough, [])

    def test_new_session_request_splits_claude_args(self):
        request = parse_new_session_request(
            name="api",
            project="~/app",
            model="an/sonnet",
            args="--permission-mode acceptEdits --add-dir ../shared",
        )

        self.assertEqual(request.name, "api")
        self.assertEqual(request.project, "~/app")
        self.assertEqual(request.model, "an/sonnet")
        self.assertEqual(
            request.passthrough,
            ["--permission-mode", "acceptEdits", "--add-dir", "../shared"],
        )

    def test_new_session_request_rejects_bad_args(self):
        with self.assertRaises(RuntimeError):
            parse_new_session_request(name="", project="", model="", args='"unterminated')

    def test_tui_mounts_headless_with_empty_sessions(self):
        class FakeManager:
            def list(self):
                return []

        async def autopilot(pilot):
            pilot.app.exit()

        CcsTuiApp(manager=FakeManager()).run(headless=True, auto_pilot=autopilot)

    def test_tui_create_then_attach_selects_created_session(self):
        from claude_switch.session import CodeSession
        from claude_switch.tui import NewSessionRequest

        class FakeManager:
            def __init__(self):
                self.sessions = []

            def list(self):
                return self.sessions

            def create_claude(self, **kwargs):
                session = CodeSession(
                    name=kwargs.get("name") or "auto-1",
                    tool="claude",
                    model=kwargs.get("model") or "ds/flash",
                    project=".",
                    index=1,
                    pid=123,
                    running=True,
                )
                self.sessions = [session]
                return session

        async def autopilot(pilot):
            app = pilot.app
            await pilot.pause()
            app._on_new_session(NewSessionRequest(None, ".", "ds/flash", []))
            await pilot.pause()
            app.action_attach()

        result = CcsTuiApp(manager=FakeManager()).run(headless=True, auto_pilot=autopilot)
        self.assertEqual(result, ("attach", "auto-1"))

    def test_tui_bindings_are_not_priority_global_bindings(self):
        keys = {binding.key: binding for binding in CcsTuiApp.BINDINGS}

        self.assertNotIn("enter", keys)
        for key in ("n", "s", "k", "r", "?", "q"):
            self.assertFalse(keys[key].priority)


if __name__ == "__main__":
    unittest.main()
