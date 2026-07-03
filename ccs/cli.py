"""Command-line interface for ccs."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .apps import APP_NAMES, LaunchPlan, LaunchRequest, build_launch_plan, get_app
from .defaults import get_default_model, load_defaults, set_default_model
from .errors import CcsError
from .memory import append_note, edit_memory, init_memory, memory_paths, read_memory, status as memory_status
from .models import (
    ModelResolutionError,
    add_model_mapping,
    list_models,
    list_providers,
    remove_model_mapping,
    resolve_model_spec,
)


HELP = """\
ccs - Code CLI Suite

Usage:
  ccs <app> [--cc-model MODEL] [--cc-auto|--cc-danger|--cc-plan] [--cc-no-memory] [--cc-dry-run] [native args...]
  ccs use [app] <model>
  ccs current
  ccs memory init|show|edit|note|task|decision|path|status
  ccs models [provider]
  ccs models add <provider/model> <actual-model>
  ccs models rm <provider/model>
  ccs providers
  ccs model show <model>

Apps:
  claude
  codex
  opencode

Examples:
  ccs memory init
  ccs use claude ds/flash
  ccs claude
  ccs claude --cc-model an/sonnet --cc-auto
  ccs codex --cc-danger "fix tests"
  ccs opencode --cc-model or/kimi-k2.6
"""

HELP_ZH = """\
ccs - Code CLI Suite

用法:
  ccs <app> [--cc-model MODEL] [--cc-auto|--cc-danger|--cc-plan] [--cc-no-memory] [--cc-dry-run] [原工具参数...]
  ccs use [app] <model>
  ccs current
  ccs memory init|show|edit|note|task|decision|path|status
  ccs models [provider]
  ccs models add <provider/model> <actual-model>
  ccs models rm <provider/model>
  ccs providers
  ccs model show <model>

示例:
  ccs memory init
  ccs use claude ds/flash
  ccs claude
  ccs claude --cc-model an/sonnet --cc-auto
  ccs codex --cc-danger "fix tests"
  ccs opencode --cc-model or/kimi-k2.6
"""

LEGACY_COMMANDS = {
    "attach",
    "daemon",
    "kill",
    "list",
    "monitor",
    "new",
    "restart",
    "switch",
    "tmux",
    "tui",
    "workbench",
}


@dataclass
class ParsedAppArgs:
    native_args: list[str]
    ccs_model: str | None = None
    quick_mode: str | None = None
    memory_enabled: bool = True
    dry_run: bool = False


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        return _main(args)
    except CcsError as exc:
        print(f"ccs: {exc}", file=sys.stderr)
        return exc.exit_code


def _main(args: list[str]) -> int:
    if not args or args[0] in {"--help", "-h", "help"}:
        print(HELP)
        return 0
    if args[0] in {"--help-zh", "help-zh"}:
        print(HELP_ZH)
        return 0
    if args[0] in {"--version", "version"}:
        print(__version__)
        return 0

    head, tail = args[0], args[1:]
    if head in APP_NAMES:
        return _run_app(head, tail)
    if head == "use":
        return _cmd_use(tail)
    if head == "current":
        return _cmd_current(tail)
    if head == "memory":
        return _cmd_memory(tail)
    if head == "models":
        return _cmd_models(tail)
    if head == "providers":
        return _cmd_providers(tail)
    if head == "model":
        return _cmd_model(tail)
    if head in LEGACY_COMMANDS:
        raise CcsError("ccs is a launcher now. Use 'ccs <app> ...'.")
    raise CcsError(f"unknown command or app '{head}'. Supported apps: {', '.join(APP_NAMES)}.")


def _run_app(app: str, args: list[str]) -> int:
    parsed = parse_app_args(args)
    default_model = None if parsed.ccs_model else get_default_model(app)
    request = LaunchRequest(
        app=app,
        native_args=parsed.native_args,
        ccs_model=parsed.ccs_model,
        default_model=default_model,
        quick_mode=parsed.quick_mode,
        memory_enabled=parsed.memory_enabled,
        dry_run=parsed.dry_run,
        cwd=Path.cwd(),
    )
    plan = build_launch_plan(request)
    if parsed.dry_run:
        _print_dry_run(plan)
        return 0
    if shutil.which(plan.executable) is None:
        raise CcsError(f"{plan.executable} not found on PATH. Install it or choose another app.", exit_code=127)
    env = os.environ.copy()
    env.update(plan.env)
    result = subprocess.run(plan.command, cwd=str(plan.cwd), env=env)
    return result.returncode


def parse_app_args(args: list[str]) -> ParsedAppArgs:
    parsed = ParsedAppArgs(native_args=[])
    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg == "--cc-model":
            parsed.ccs_model = _take_value(args, idx, arg)
            idx += 2
        elif arg.startswith("--cc-model="):
            parsed.ccs_model = arg.split("=", 1)[1]
            idx += 1
        elif arg in {"--cc-auto", "--cc-danger", "--cc-plan"}:
            mode = arg.removeprefix("--cc-")
            if parsed.quick_mode and parsed.quick_mode != mode:
                raise CcsError("choose only one of --cc-auto, --cc-danger, --cc-plan.")
            parsed.quick_mode = mode
            idx += 1
        elif arg == "--cc-no-memory":
            parsed.memory_enabled = False
            idx += 1
        elif arg == "--cc-dry-run":
            parsed.dry_run = True
            idx += 1
        elif arg.startswith("--cc-"):
            raise CcsError(f"unknown ccs option '{arg}'")
        else:
            parsed.native_args.append(arg)
            idx += 1
    return parsed


def _take_value(args: list[str], index: int, flag: str) -> str:
    if index + 1 >= len(args):
        raise CcsError(f"{flag} requires a value")
    value = args[index + 1]
    if value.startswith("--cc-"):
        raise CcsError(f"{flag} requires a value")
    return value


def _cmd_use(args: list[str]) -> int:
    if len(args) == 1:
        app = None
        model = args[0]
    elif len(args) == 2:
        app, model = args
        get_app(app)
    else:
        raise CcsError("usage: ccs use [app] <model>")
    resolved = resolve_model_spec(model)
    set_default_model(resolved.canonical, app)
    if app:
        print(f"{app}: {resolved.canonical}")
    else:
        print(f"default: {resolved.canonical}")
    return 0


def _cmd_current(args: list[str]) -> int:
    if args:
        raise CcsError("usage: ccs current")
    defaults = load_defaults()
    print(f"default: {defaults.global_model or '-'}")
    for app in APP_NAMES:
        print(f"{app}: {defaults.app_models.get(app) or '-'}")
    return 0


def _cmd_memory(args: list[str]) -> int:
    if not args:
        raise CcsError("usage: ccs memory init|show|edit|note|task|decision|path|status")
    cmd, rest = args[0], args[1:]
    if cmd == "init":
        if rest:
            raise CcsError("usage: ccs memory init")
        print(init_memory().memory)
        return 0
    if cmd == "show":
        if rest:
            raise CcsError("usage: ccs memory show")
        print(read_memory(), end="")
        return 0
    if cmd == "edit":
        if rest:
            raise CcsError("usage: ccs memory edit")
        return edit_memory()
    if cmd in {"note", "task", "decision"}:
        if not rest:
            raise CcsError(f"usage: ccs memory {cmd} <text>")
        paths = append_note(cmd, " ".join(rest))
        print(paths.memory)
        return 0
    if cmd == "path":
        if rest:
            raise CcsError("usage: ccs memory path")
        print(memory_paths().memory)
        return 0
    if cmd == "status":
        if rest:
            raise CcsError("usage: ccs memory status")
        print(memory_status())
        return 0
    if cmd in {"compact", "harvest"}:
        raise CcsError(f"ccs memory {cmd} is reserved by the design but not implemented yet.")
    raise CcsError(f"unknown memory command '{cmd}'")


def _cmd_models(args: list[str]) -> int:
    if not args:
        models = list_models()
    elif args[0] == "add":
        if len(args) != 3:
            raise CcsError("usage: ccs models add <provider/model> <actual-model>")
        add_model_mapping(args[1], args[2])
        print(f"added {args[1]} -> {args[2]}")
        return 0
    elif args[0] == "rm":
        if len(args) != 2:
            raise CcsError("usage: ccs models rm <provider/model>")
        if not remove_model_mapping(args[1]):
            raise CcsError(f"model mapping '{args[1]}' not found")
        print(f"removed {args[1]}")
        return 0
    elif len(args) == 1:
        models = list_models(args[0])
    else:
        raise CcsError("usage: ccs models [provider]")
    for spec in models:
        print(f"{spec.model_spec:<28} {spec.actual_model:<32} {spec.source}")
    return 0


def _cmd_providers(args: list[str]) -> int:
    if args:
        raise CcsError("usage: ccs providers")
    for provider in list_providers():
        env = provider.env_key or "-"
        status = "set" if provider.env_is_set else "missing"
        print(f"{provider.id:<12} {env:<24} {status}")
    return 0


def _cmd_model(args: list[str]) -> int:
    if len(args) != 2 or args[0] != "show":
        raise CcsError("usage: ccs model show <model>")
    resolved = resolve_model_spec(args[1])
    print(f"input: {resolved.input}")
    print(f"canonical: {resolved.canonical}")
    print(f"provider: {resolved.provider}")
    print(f"actual_model: {resolved.actual_model}")
    print(f"source: {resolved.source}")
    if resolved.env_key:
        print(f"env: {resolved.env_key} ({'set' if resolved.env_is_set else 'missing'})")
    return 0


def _print_dry_run(plan: LaunchPlan) -> None:
    for warning in plan.warnings:
        print(f"warning: {warning}")
    print(f"cwd: {plan.cwd}")
    if plan.env:
        print("env:")
        for key, value in sorted(plan.env.items()):
            display = "<set>" if "TOKEN" in key or "KEY" in key else value
            print(f"  {key}={display}")
    print(f"command: {shlex.join(plan.command)}")


__all__ = ["HELP", "HELP_ZH", "main", "parse_app_args"]

