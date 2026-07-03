from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from ccs.apps import LaunchRequest, build_launch_plan
from ccs.cli import HELP, main, parse_app_args
from ccs.defaults import get_default_model, set_default_model
from ccs.memory import append_note, init_memory, memory_paths, read_memory, resolve_memory_root
from ccs.models import (
    ModelResolutionError,
    add_model_mapping,
    list_models,
    resolve_model_spec,
)


class ArgParseTests(unittest.TestCase):
    def test_parse_cc_args_preserves_native_order(self):
        parsed = parse_app_args(["--cc-model", "ds/flash", "--permission-mode", "auto", "hello"])

        self.assertEqual(parsed.ccs_model, "ds/flash")
        self.assertEqual(parsed.native_args, ["--permission-mode", "auto", "hello"])

    def test_modes_are_mutually_exclusive(self):
        with self.assertRaisesRegex(Exception, "choose only one"):
            parse_app_args(["--cc-auto", "--cc-plan"])

    def test_unknown_cc_option_errors(self):
        with self.assertRaisesRegex(Exception, "unknown ccs option"):
            parse_app_args(["--cc-name", "old"])

    def test_help_has_no_legacy_commands(self):
        self.assertNotIn("ccs tmux", HELP)
        self.assertNotIn("ccs tui", HELP)
        self.assertNotIn("claude-switch", HELP)


class ModelTests(unittest.TestCase):
    def test_resolves_strict_provider_model(self):
        resolved = resolve_model_spec("ds/flash")

        self.assertEqual(resolved.provider, "deepseek")
        self.assertEqual(resolved.canonical, "ds/flash")
        self.assertEqual(resolved.actual_model, "deepseek-v4-flash")

    def test_legacy_profile_name_is_not_supported(self):
        with self.assertRaises(ModelResolutionError):
            resolve_model_spec("deepseek-flash")

    def test_custom_model_mapping_uses_ccs_home(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"CCS_HOME": td}, clear=False):
            add_model_mapping("or/qwen3-coder", "qwen/qwen3-coder")
            resolved = resolve_model_spec("or/qwen3-coder")

        self.assertEqual(resolved.actual_model, "qwen/qwen3-coder")
        self.assertEqual(resolved.source, "custom")

    def test_list_models_filters_provider(self):
        models = list_models("openai")

        self.assertEqual([m.model_spec for m in models], ["openai/gpt-5"])


class DefaultsTests(unittest.TestCase):
    def test_use_sets_app_default(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"CCS_HOME": td}, clear=False):
            set_default_model("ds/flash", "claude")

            self.assertEqual(get_default_model("claude"), "ds/flash")
            self.assertTrue((Path(td) / "config.toml").exists())

    def test_global_default_applies_when_app_missing(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"CCS_HOME": td}, clear=False):
            set_default_model("openai/gpt-5")

            self.assertEqual(get_default_model("codex"), "openai/gpt-5")


class MemoryTests(unittest.TestCase):
    def test_memory_root_prefers_git_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            (root / ".git").mkdir()
            nested = root / "a" / "b"
            nested.mkdir(parents=True)

            self.assertEqual(resolve_memory_root(nested), root / ".ccs")

    def test_memory_root_ignores_home_ccs(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as home:
            root = Path(td).resolve()
            fake_home = Path(home).resolve()
            (fake_home / ".ccs").mkdir()
            with patch("pathlib.Path.home", return_value=fake_home):
                self.assertEqual(resolve_memory_root(root), root / ".ccs")

    def test_init_memory_writes_template_and_gitignore(self):
        with tempfile.TemporaryDirectory() as td:
            paths = init_memory(td)

            self.assertTrue(paths.memory.exists())
            self.assertIn("# CCS Memory", paths.memory.read_text())
            self.assertIn("memory.local.md", paths.gitignore.read_text())

    def test_memory_append_note_task_decision(self):
        with tempfile.TemporaryDirectory() as td:
            append_note("note", "进展", td)
            append_note("task", "待办", td)
            append_note("decision", "决策", td)

            content = read_memory(td)

        self.assertIn("[ccs] 进展", content)
        self.assertIn("[ ]", content)
        self.assertIn("[ccs] 决策", content)


class LaunchPlanTests(unittest.TestCase):
    def test_claude_plan_uses_model_mode_and_memory(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(
            os.environ, {"DEEPSEEK_API_KEY": "sk-test"}, clear=False
        ):
            plan = build_launch_plan(
                LaunchRequest(
                    app="claude",
                    ccs_model="ds/flash",
                    quick_mode="auto",
                    native_args=["--add-dir", "../shared"],
                    cwd=Path(td),
                )
            )

        self.assertEqual(plan.executable, "claude")
        self.assertIn("--model", plan.argv)
        self.assertIn("deepseek-v4-flash", plan.argv)
        self.assertIn("--permission-mode", plan.argv)
        self.assertIn("auto", plan.argv)
        self.assertIn("--append-system-prompt", plan.argv)
        self.assertEqual(plan.env["ANTHROPIC_BASE_URL"], "https://api.deepseek.com/anthropic")
        self.assertEqual(plan.env["ANTHROPIC_AUTH_TOKEN"], "sk-test")

    def test_native_model_conflicts_with_cc_model(self):
        with self.assertRaisesRegex(Exception, "model is specified twice"):
            build_launch_plan(
                LaunchRequest(
                    app="codex",
                    ccs_model="openai/gpt-5",
                    native_args=["--model", "gpt-4"],
                    memory_enabled=False,
                )
            )

    def test_default_model_is_injected_when_native_model_absent(self):
        plan = build_launch_plan(
            LaunchRequest(
                app="codex",
                default_model="openai/gpt-5",
                native_args=["--sandbox", "workspace-write"],
                memory_enabled=False,
            )
        )

        self.assertEqual(plan.command[:3], ["codex", "--model", "gpt-5"])
        self.assertEqual(plan.argv[-2:], ["--sandbox", "workspace-write"])

    def test_native_model_suppresses_default_model(self):
        plan = build_launch_plan(
            LaunchRequest(
                app="codex",
                default_model="openai/gpt-5",
                native_args=["--model", "native-model"],
                memory_enabled=False,
            )
        )

        self.assertEqual(plan.command, ["codex", "--model", "native-model"])

    def test_codex_plan_mode_is_unsupported(self):
        with self.assertRaisesRegex(Exception, "--cc-plan is not supported for codex"):
            build_launch_plan(LaunchRequest(app="codex", quick_mode="plan", native_args=[], memory_enabled=False))

    def test_codex_exec_preserves_subcommand(self):
        with tempfile.TemporaryDirectory() as td:
            plan = build_launch_plan(LaunchRequest(app="codex", native_args=["exec", "fix tests"], cwd=Path(td)))

        self.assertEqual(plan.argv[0], "exec")
        self.assertIn("User request:\nfix tests", plan.argv[1])

    def test_opencode_danger_warns_and_expands_to_auto(self):
        plan = build_launch_plan(LaunchRequest(app="opencode", quick_mode="danger", native_args=[], memory_enabled=False))

        self.assertEqual(plan.command, ["opencode", "--auto"])
        self.assertIn("opencode has no stronger danger flag", plan.warnings[0])

    def test_opencode_run_combines_memory_with_message(self):
        with tempfile.TemporaryDirectory() as td:
            plan = build_launch_plan(LaunchRequest(app="opencode", native_args=["run", "review this"], cwd=Path(td)))

        self.assertEqual(plan.argv[0], "run")
        self.assertIn("User request:\nreview this", plan.argv[1])

    def test_passthrough_help_does_not_create_memory(self):
        with tempfile.TemporaryDirectory() as td:
            plan = build_launch_plan(LaunchRequest(app="claude", native_args=["--help"], cwd=Path(td)))

            self.assertEqual(plan.command, ["claude", "--help"])
            self.assertFalse((Path(td) / ".ccs").exists())

    def test_no_memory_disables_prompt_injection(self):
        plan = build_launch_plan(
            LaunchRequest(app="claude", ccs_model="an/sonnet", native_args=[], memory_enabled=False)
        )

        self.assertNotIn("--append-system-prompt", plan.argv)


class CliCommandTests(unittest.TestCase):
    def test_main_use_and_current(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"CCS_HOME": td}, clear=False):
            self.assertEqual(main(["use", "claude", "ds/flash"]), 0)
            self.assertEqual(get_default_model("claude"), "ds/flash")

    def test_unknown_legacy_command_errors(self):
        with patch("sys.stderr") as stderr:
            code = main(["tmux", "list"])

        self.assertEqual(code, 1)
        self.assertTrue(stderr.write.called)

    def test_memory_commands(self):
        with tempfile.TemporaryDirectory() as td:
            old = os.getcwd()
            os.chdir(td)
            try:
                self.assertEqual(main(["memory", "init"]), 0)
                self.assertEqual(main(["memory", "note", "hello"]), 0)
                content = (Path(td) / ".ccs" / "memory.md").read_text()
            finally:
                os.chdir(old)

        self.assertIn("hello", content)


class SystemCliTests(unittest.TestCase):
    def test_fake_claude_receives_full_launch_plan(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            output = root / "out.json"
            fake = bin_dir / "claude"
            fake.write_text(
                textwrap.dedent(
                    f"""\
                    #!{sys.executable}
                    import json, os, sys
                    data = {{
                        "argv": sys.argv[1:],
                        "base_url": os.environ.get("ANTHROPIC_BASE_URL"),
                        "token": bool(os.environ.get("ANTHROPIC_AUTH_TOKEN")),
                    }}
                    open({str(output)!r}, "w").write(json.dumps(data))
                    """
                )
            )
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

            project = root / "project"
            project.mkdir()
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                    "PYTHONPATH": str(Path.cwd()),
                    "CCS_HOME": str(root / "home"),
                    "DEEPSEEK_API_KEY": "sk-test",
                }
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ccs",
                    "claude",
                    "--cc-model",
                    "ds/flash",
                    "--cc-auto",
                    "--add-dir",
                    "../shared",
                ],
                cwd=project,
                env=env,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(output.read_text())

            self.assertIn("--model", data["argv"])
            self.assertIn("deepseek-v4-flash", data["argv"])
            self.assertIn("--permission-mode", data["argv"])
            self.assertIn("auto", data["argv"])
            self.assertIn("--append-system-prompt", data["argv"])
            self.assertEqual(data["base_url"], "https://api.deepseek.com/anthropic")
            self.assertTrue(data["token"])
            self.assertTrue((project / ".ccs" / "memory.md").exists())

    def test_dry_run_does_not_create_memory(self):
        with tempfile.TemporaryDirectory() as td:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path.cwd())
            result = subprocess.run(
                [sys.executable, "-m", "ccs", "codex", "--cc-model", "openai/gpt-5", "--cc-dry-run"],
                cwd=td,
                env=env,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("command: codex --model gpt-5", result.stdout)
            self.assertFalse((Path(td) / ".ccs").exists())


if __name__ == "__main__":
    unittest.main()
