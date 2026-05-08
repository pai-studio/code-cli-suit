"""Unified code-session launcher."""

from __future__ import annotations

import subprocess
import sys
import shlex
import json
from dataclasses import dataclass
from pathlib import Path
import time

from .models import (
    ModelResolutionError,
    add_model_mapping,
    list_models,
    list_providers,
    remove_model_mapping,
    resolve_model_spec,
    validate_runtime_key,
)
from .session import SessionManager


HELP = """\
ccs — run Claude Code sessions with provider/model

QUICK START
  ccs models
      List built-in provider/model shortcuts.

  export DEEPSEEK_API_KEY="sk-..."
      ccs reads API keys from environment variables. It does not store keys.

  ccs claude --cc-model ds/flash
      Start Claude Code in the current directory with DeepSeek Flash.

  ccs claude --cc-model sonnet --permission-mode acceptEdits
      Start a managed Claude session and pass --permission-mode to Claude itself.

  ccs claude --help
      Show the original Claude help. If no --cc-* option is present, ccs simply
      forwards all arguments to the original tool.

COMMON EXAMPLES
  ccs providers
  ccs models
  ccs tui
  ccs model show or/kimi-k2.6
  ccs claude --cc-model ds/flash
  ccs claude --cc-model ds/pro --cc-name api-review
  ccs claude --cc-model or/kimi-k2.6 --cc-project ~/work/app
  ccs claude --cc-model an/sonnet --cc-no-attach
  ccs claude --cc-model ds/flash --cc-dry-run
  ccs claude --cc-model sonnet --permission-mode acceptEdits --add-dir ../shared
  ccs models add or/qwen3-coder qwen/qwen3-coder

SESSION MANAGEMENT
  ccs tui
      Open the interactive session dashboard.
      Attached sessions stay focused on the Claude terminal.

  ccs list
      List managed sessions.

  ccs list --json
      Print managed sessions as JSON.

  ccs attach
      Attach to the most recent managed session.

  ccs attach <name>
      Attach to a named session.

  ccs kill <name>
      Kill a managed session and remove its session settings file.

  ccs monitor [name...] [--lines N]
      Watch recent output from one or more sessions without attaching.

  ccs switch <name> [model]
      Restart a session. If model is provided, switch to it first.

  ccs switch <name> [model] --create
      Create the session if it does not exist.

MODEL SPEC
  an/sonnet             Anthropic Sonnet
  ds/flash              DeepSeek Flash
  ds/pro                DeepSeek Pro
  or/kimi-k2.6          OpenRouter Kimi K2.6
  mm/m2.7               MiniMax M2.7

OPENROUTER
  ccs keeps the user-facing model spec as provider/model.
  OpenRouter author/model ids are mapped internally:
    or/kimi-k2.6 -> moonshotai/kimi-k2.6
  Add your own mapping:
    ccs models add or/qwen3-coder qwen/qwen3-coder

MENTAL MODEL
  ccs only reads options whose names start with --cc-.
  Everything else after `ccs claude` belongs to Claude and is passed through.

  Managed session:
    ccs claude --cc-model ds/flash --permission-mode acceptEdits

  Plain Claude passthrough:
    ccs claude --help
    ccs claude auth
    ccs claude doctor

CCS OPTIONS
  --cc-model <model>     provider/model for this session
  --cc-name <name>       session name; auto-generated when omitted
  --cc-project <dir>     project directory; defaults to current directory
  --cc-no-attach         create the session without attaching
  --cc-dry-run           print generated command without creating a session

REQUIREMENTS
  tmux and claude must be available on PATH for managed Claude sessions.
  API keys are read from environment variables, for example DEEPSEEK_API_KEY.

IN-SESSION KEYS
  F2                    ccs session picker
  F3                    previous session
  F4                    next session
  F10                   detach; Claude keeps running
  Ctrl-b s              session picker fallback
  Ctrl-b n / Ctrl-b p   next / previous session fallback
  Ctrl-b d              detach fallback

COMMAND SUMMARY
  ccs claude [claude args...] [--cc-model MODEL]
  ccs models [provider]
  ccs models add <provider/model-alias> <actual-model>
  ccs models rm <provider/model-alias>
  ccs providers
  ccs model show <model>
  ccs tui
  ccs list
  ccs list --json
  ccs attach [name]
  ccs kill <name>
  ccs switch <name> [model]
  ccs monitor [name...]
"""

HELP_ZH = """\
ccs — 用 provider/model 运行 Claude Code 会话

快速开始
  ccs models
      查看内置 provider/model 快捷名。

  export DEEPSEEK_API_KEY="sk-..."
      ccs 只从环境变量读取 API key，不保存密钥。

  ccs claude --cc-model ds/flash
      在当前目录用 DeepSeek Flash 启动 Claude Code。

  ccs claude --cc-model sonnet --permission-mode acceptEdits
      启动托管 Claude 会话，并把 --permission-mode 原样传给 Claude。

  ccs claude --help
      显示原始 Claude 帮助。只要没有 --cc-* 参数，ccs 就会把所有参数
      原样转发给原始工具。

常用示例
  ccs providers
  ccs models
  ccs tui
  ccs model show or/kimi-k2.6
  ccs claude --cc-model ds/flash
  ccs claude --cc-model ds/pro --cc-name api-review
  ccs claude --cc-model or/kimi-k2.6 --cc-project ~/work/app
  ccs claude --cc-model an/sonnet --cc-no-attach
  ccs claude --cc-model ds/flash --cc-dry-run
  ccs claude --cc-model sonnet --permission-mode acceptEdits --add-dir ../shared
  ccs models add or/qwen3-coder qwen/qwen3-coder

会话管理
  ccs tui
      打开交互式 session 管理界面。
      进入会话后默认保持 Claude 终端全屏。

  ccs list
      列出托管会话。

  ccs list --json
      以 JSON 格式输出托管会话。

  ccs attach
      进入最近的托管会话。

  ccs attach <name>
      进入指定会话。

  ccs kill <name>
      删除托管会话，并清理该会话的 settings 文件。

  ccs monitor [name...] [--lines N]
      在普通命令行同时查看一个或多个 session 的最近输出，不进入 Claude。

  ccs switch <name> [model]
      重启会话。传 model 时先切换到该模型。

  ccs switch <name> [model] --create
      如果会话不存在，则创建它。

模型写法
  an/sonnet             Anthropic Sonnet
  ds/flash              DeepSeek Flash
  ds/pro                DeepSeek Pro
  or/kimi-k2.6          OpenRouter Kimi K2.6
  mm/m2.7               MiniMax M2.7

OpenRouter
  用户侧模型名保持 provider/model 两段式。
  OpenRouter 的 author/model 在内部映射：
    or/kimi-k2.6 -> moonshotai/kimi-k2.6
  添加自定义映射：
    ccs models add or/qwen3-coder qwen/qwen3-coder

心智模型
  ccs 只读取 --cc- 开头的参数。
  `ccs claude` 后面的其他参数都属于 Claude，会被原样传给 Claude。

  托管会话:
    ccs claude --cc-model ds/flash --permission-mode acceptEdits

  原始 Claude 透传:
    ccs claude --help
    ccs claude auth
    ccs claude doctor

ccs 参数
  --cc-model <model>     当前会话使用的 provider/model
  --cc-name <name>       会话名；不填则自动生成
  --cc-project <dir>     项目目录；默认当前目录
  --cc-no-attach         创建会话后不自动进入
  --cc-dry-run           打印生成的命令，不创建会话

依赖
  托管 Claude 会话需要 tmux 和 claude 在 PATH 中可用。
  API key 只从环境变量读取，例如 DEEPSEEK_API_KEY。

会话内快捷键
  F2                    打开 ccs session 选择器
  F3                    切到上一个 session
  F4                    切到下一个 session
  F10                   退出当前附着；Claude 继续后台运行
  Ctrl-b s              session 选择器备用方式
  Ctrl-b n / Ctrl-b p   下一个 / 上一个 session 备用方式
  Ctrl-b d              detach 备用方式

命令摘要
  ccs claude [claude args...] [--cc-model MODEL]
  ccs models [provider]
  ccs models add <provider/model-alias> <actual-model>
  ccs models rm <provider/model-alias>
  ccs providers
  ccs model show <model>
  ccs tui
  ccs list
  ccs list --json
  ccs attach [name]
  ccs kill <name>
  ccs switch <name> [model]
  ccs monitor [name...]
"""


TOOLS = {"claude", "codex", "opencode"}
MANAGEMENT = {
    "list",
    "attach",
    "kill",
    "switch",
    "help",
    "models",
    "providers",
    "model",
    "tui",
    "sidebar",
    "pick",
    "select",
    "focus",
    "monitor",
}


@dataclass
class CcsOptions:
    model: str | None = None
    name: str | None = None
    project: str = "."
    no_attach: bool = False
    reuse: str | None = None
    dry_run: bool = False


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"--help-zh", "help-zh"}:
        print(HELP_ZH)
        return
    if not args or args[0] in {"-h", "--help", "help"}:
        print(HELP)
        return

    head, rest = args[0], args[1:]
    if head in MANAGEMENT:
        _run_management(head, rest)
        return
    if head in TOOLS:
        _run_tool(head, rest)
        return

    print(f"ccs: unknown command or tool '{head}'", file=sys.stderr)
    print("tip: run 'ccs --help'", file=sys.stderr)
    sys.exit(2)


def _run_management(command: str, args: list[str]) -> None:
    if command == "help":
        print(HELP)
        return
    if command == "models":
        _run_models(args)
        return
    if command == "providers":
        _run_providers(args)
        return
    if command == "model":
        _run_model(args)
        return
    if command == "tui":
        _run_tui(args)
        return
    if command == "sidebar":
        _run_sidebar(args)
        return
    if command == "pick":
        _run_pick(args)
        return
    if command == "select":
        _run_select(args)
        return
    if command == "focus":
        _run_focus(args)
        return
    mgr = _manager()
    try:
        if command == "list":
            if args == ["--json"]:
                _print_sessions_json(mgr)
            elif args:
                raise RuntimeError("usage: ccs list [--json]")
            else:
                _print_sessions(mgr)
        elif command == "attach":
            if len(args) > 1:
                raise RuntimeError("usage: ccs attach [name]")
            mgr.attach(args[0] if args else None)
        elif command == "kill":
            if len(args) != 1:
                raise RuntimeError("usage: ccs kill <name>")
            mgr.kill(args[0])
            print(f"Killed session '{args[0]}'")
        elif command == "switch":
            _run_switch(mgr, args)
        elif command == "monitor":
            _run_monitor(mgr, args)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _run_tool(tool: str, args: list[str]) -> None:
    opts, passthrough, managed = _parse_cc_options(args)
    if tool != "claude":
        if managed:
            print(f"ccs: managed sessions for '{tool}' are not implemented yet", file=sys.stderr)
            sys.exit(1)
        _exec_tool(tool, passthrough)
        return

    if not managed:
        _exec_tool("claude", passthrough)
        return

    name = opts.name
    project = opts.project
    if opts.dry_run and not opts.reuse:
        _print_claude_dry_run(name, project, opts.model, passthrough)
        return

    mgr = _manager()
    if opts.reuse:
        try:
            session = mgr.switch_model(
                name=opts.reuse,
                model=opts.model,
                passthrough=passthrough if passthrough else None,
                attach=not opts.no_attach,
                dry_run=opts.dry_run,
            )
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        if session is not None and opts.no_attach:
            print(f"Updated session '{session.name}' ({session.tool}, {session.model})")
        return

    try:
        session = mgr.create_claude(
            name=name,
            project=project,
            model=opts.model,
            passthrough=passthrough,
            attach=not opts.no_attach,
            dry_run=opts.dry_run,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if session is not None and opts.no_attach:
        print(f"Created session '{session.name}' ({session.tool}, {session.model})")


def _run_switch(mgr: SessionManager, args: list[str]) -> None:
    create = False
    no_attach = False
    project = "."
    positional: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--create":
            create = True
            i += 1
        elif arg == "--cc-no-attach":
            no_attach = True
            i += 1
        elif arg == "--cc-project":
            project = _take_value(args, i, arg)
            i += 2
        elif arg.startswith("--"):
            raise RuntimeError(f"unknown switch option: {arg}")
        else:
            positional.append(arg)
            i += 1
    if not 1 <= len(positional) <= 2:
        raise RuntimeError(
            "usage: ccs switch <name> [model] [--create] [--cc-project DIR] [--cc-no-attach]"
        )
    name = positional[0]
    model = positional[1] if len(positional) == 2 else None
    exists = any(session.name == name for session in mgr.list())
    session = mgr.switch_model(
        name=name,
        model=model,
        create=create,
        project=project,
        attach=create and not exists and not no_attach,
    )
    if session is not None:
        print(f"Switched session '{session.name}' to {session.model}")


def _run_models(args: list[str]) -> None:
    if args[:1] == ["add"]:
        if len(args) != 3:
            raise SystemExit("ccs: usage: ccs models add <provider/model-alias> <actual-model>")
        try:
            add_model_mapping(args[1], args[2])
        except ModelResolutionError as exc:
            raise SystemExit(f"ccs: {exc}") from None
        print(f"Added model mapping {args[1]} -> {args[2]}")
        return
    if args[:1] in (["rm"], ["remove"], ["delete"]):
        if len(args) != 2:
            raise SystemExit("ccs: usage: ccs models rm <provider/model-alias>")
        try:
            removed = remove_model_mapping(args[1])
        except ModelResolutionError as exc:
            raise SystemExit(f"ccs: {exc}") from None
        if not removed:
            raise SystemExit(f"ccs: model mapping '{args[1]}' not found")
        print(f"Removed model mapping {args[1]}")
        return

    json_mode = False
    provider = None
    for arg in args:
        if arg == "--json":
            json_mode = True
        elif provider is None:
            provider = arg
        else:
            raise SystemExit("ccs: usage: ccs models [provider] [--json]")
    try:
        models = list_models(provider)
    except ModelResolutionError as exc:
        raise SystemExit(f"ccs: {exc}") from None
    if json_mode:
        print(
            json.dumps(
                [
                    {
                        "provider": model.provider,
                        "model": model.name,
                        "model_spec": model.model_spec,
                        "actual_model": model.actual_model,
                        "aliases": list(model.aliases),
                        "legacy_profiles": list(model.legacy_profiles),
                        "source": model.source,
                    }
                    for model in models
                ],
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    hdr = f"{'Provider':<12} {'Alias':<7} {'Model Spec':<24} Actual Model"
    print(hdr)
    print("-" * len(hdr))
    for model in models:
        alias = {
            "anthropic": "an",
            "deepseek": "ds",
            "openrouter": "or",
            "minimax": "mm",
        }.get(model.provider, model.provider)
        print(f"{model.provider:<12} {alias:<7} {model.model_spec:<24} {model.actual_model}")


def _run_providers(args: list[str]) -> None:
    if args not in ([], ["--json"]):
        raise SystemExit("ccs: usage: ccs providers [--json]")
    providers = list_providers()
    if args == ["--json"]:
        print(
            json.dumps(
                [
                    {
                        "id": provider.id,
                        "aliases": list(provider.aliases),
                        "name": provider.name,
                        "base_url": provider.base_url,
                        "env_key": provider.env_key,
                        "key": "set" if provider.env_is_set else "missing",
                        "auth_mode": provider.auth_mode,
                        "desc": provider.desc,
                    }
                    for provider in providers
                ],
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    hdr = f"{'Provider':<12} {'Aliases':<16} {'Env Key':<24} Key"
    print(hdr)
    print("-" * len(hdr))
    for provider in providers:
        key = "set" if provider.env_is_set else "missing"
        env_key = provider.env_key or "-"
        print(f"{provider.id:<12} {','.join(provider.aliases):<16} {env_key:<24} {key}")


def _run_model(args: list[str]) -> None:
    if len(args) != 2 or args[0] != "show":
        raise SystemExit("ccs: usage: ccs model show <model>")
    try:
        resolved = resolve_model_spec(args[1])
    except ModelResolutionError as exc:
        raise SystemExit(f"ccs: {exc}") from None
    print(f"Input:       {resolved.input}")
    print(f"Provider:    {resolved.provider}")
    print(f"Env Key:     {resolved.env_key or '-'}")
    print(f"Key:         {'set' if resolved.env_is_set else 'missing'}")
    print(f"Model:       {resolved.actual_model}")
    print(f"Canonical:   {resolved.canonical}")
    print(f"Source:      {resolved.source}")
    if resolved.legacy_profile:
        print(f"Legacy:      {resolved.legacy_profile}")


def _run_tui(args: list[str]) -> None:
    if args:
        raise SystemExit("ccs: usage: ccs tui")
    try:
        from .tui import run_tui
    except ModuleNotFoundError as exc:
        if exc.name == "textual":
            print("Error: textual is required for ccs tui.", file=sys.stderr)
            print("Install with: pip install -e .", file=sys.stderr)
            sys.exit(1)
        raise

    try:
        action = run_tui()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    if action and action[0] == "attach":
        try:
            SessionManager().attach(action[1])
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)


def _run_sidebar(args: list[str]) -> None:
    current, main_pane = _parse_sidebar_args(args)

    try:
        mgr = SessionManager()
        while True:
            sessions = mgr.list()
            print("\033[H\033[2J", end="")
            print("\033[1mccs\033[0m")
            if not sessions:
                print("No sessions")
            for session in sessions:
                marker = ">" if session.name == current else " "
                status = "*" if session.running else "x"
                model = _clip(session.model, 16)
                name = _clip(session.name, 18)
                print(f"{marker} {name}")
                print(f"  {status} {model}")
            print("")
            print("F2  sessions")
            print("F3/F4 prev/next")
            print("F10 leave")
            sys.stdout.flush()
            if main_pane:
                subprocess.run(
                    ["tmux", "select-pane", "-t", main_pane],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
            time.sleep(1)
    except KeyboardInterrupt:
        return
    except RuntimeError as exc:
        print(f"ccs sidebar: {exc}", file=sys.stderr)
        time.sleep(3)


def _run_pick(args: list[str]) -> None:
    if args:
        raise SystemExit("ccs: usage: ccs pick")
    try:
        import curses
    except ModuleNotFoundError:
        raise SystemExit("ccs: curses is required for ccs pick") from None

    mgr = SessionManager()
    sessions = mgr.list()
    if not sessions:
        print("No ccs sessions")
        time.sleep(1)
        return

    current = mgr.current_session_name()
    selected = curses.wrapper(_pick_session, sessions, current)
    if selected:
        mgr.attach(selected)


def _run_select(args: list[str]) -> None:
    if len(args) != 1 or args[0] not in {"next", "prev"}:
        raise SystemExit("ccs: usage: ccs select next|prev")
    try:
        SessionManager().select_relative(args[0])
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _run_focus(args: list[str]) -> None:
    if len(args) > 1:
        raise SystemExit("ccs: usage: ccs focus [name]")
    try:
        SessionManager().focus(args[0] if args else None)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _run_monitor(mgr: SessionManager, args: list[str]) -> None:
    names, lines, interval, once = _parse_monitor_args(args)
    try:
        while True:
            sessions = mgr.list()
            if names:
                wanted = set(names)
                sessions = [session for session in sessions if session.name in wanted]
                missing = wanted - {session.name for session in sessions}
                if missing:
                    raise RuntimeError(f"session not found: {', '.join(sorted(missing))}")
            print("\033[H\033[2J", end="")
            print("ccs monitor")
            print("Ctrl-C quit | ccs attach <name> to interact")
            print("")
            if not sessions:
                print("No sessions.")
            for session in sessions:
                status = "running" if session.running else "stopped"
                print(f"===== {session.name} | {session.tool} | {session.model} | {status} =====")
                try:
                    output = mgr.capture(session.name, lines=lines)
                except RuntimeError as exc:
                    output = f"[capture failed: {exc}]"
                print(_tail_nonempty(output, lines))
                print("")
            sys.stdout.flush()
            if once:
                return
            time.sleep(interval)
    except KeyboardInterrupt:
        return


def _parse_monitor_args(args: list[str]) -> tuple[list[str], int, float, bool]:
    names: list[str] = []
    lines = 30
    interval = 2.0
    once = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--lines":
            lines = int(_take_value(args, i, arg))
            i += 2
        elif arg == "--interval":
            interval = float(_take_value(args, i, arg))
            i += 2
        elif arg == "--once":
            once = True
            i += 1
        elif arg.startswith("--"):
            raise SystemExit(f"ccs: unknown monitor option: {arg}")
        else:
            names.append(arg)
            i += 1
    if lines < 1:
        raise SystemExit("ccs: --lines must be >= 1")
    if interval <= 0:
        raise SystemExit("ccs: --interval must be > 0")
    return names, lines, interval, once


def _tail_nonempty(output: str, lines: int) -> str:
    rows = [row.rstrip() for row in output.splitlines()]
    while rows and not rows[-1]:
        rows.pop()
    return "\n".join(rows[-lines:]) if rows else ""


def _pick_session(stdscr, sessions, current: str | None = None) -> str | None:
    import curses

    try:
        curses.curs_set(0)
    except curses.error:
        pass
    selected = 0
    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        stdscr.addnstr(0, 0, "ccs sessions", width - 1, curses.A_BOLD)
        stdscr.addnstr(1, 0, "Enter switch   * current   > cursor   q close", width - 1)
        max_rows = max(1, height - 4)
        start = max(0, selected - max_rows + 1)
        visible = sessions[start : start + max_rows]
        for offset, session in enumerate(visible):
            index = start + offset
            marker = _session_picker_marker(
                is_selected=index == selected,
                is_current=session.name == current,
            )
            status = "running" if session.running else "stopped"
            text = f"{marker} {session.name}  {session.model}  {session.project_name}  {status}"
            attr = curses.A_REVERSE if index == selected else curses.A_NORMAL
            stdscr.addnstr(offset + 3, 0, text, width - 1, attr)
        stdscr.refresh()

        key = stdscr.getch()
        if key in (ord("q"), ord("Q"), 27):
            return None
        if key in (curses.KEY_UP, ord("k")):
            selected = max(0, selected - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            selected = min(len(sessions) - 1, selected + 1)
        elif key in (10, 13, curses.KEY_ENTER):
            return sessions[selected].name


def _session_picker_marker(*, is_selected: bool, is_current: bool) -> str:
    if is_selected and is_current:
        return ">*"
    if is_selected:
        return "> "
    if is_current:
        return " *"
    return "  "


def _parse_sidebar_args(args: list[str]) -> tuple[str | None, str | None]:
    current = None
    main_pane = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--current":
            current = _take_value(args, i, arg)
            i += 2
        elif arg == "--main-pane":
            main_pane = _take_value(args, i, arg)
            i += 2
        else:
            break
    if i != len(args):
        raise SystemExit("ccs: usage: ccs sidebar [--current NAME] [--main-pane PANE]")
    return current, main_pane


def _clip(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    return value[: max(0, width - 1)] + "…"


def _print_claude_dry_run(
    name: str | None,
    project: str,
    model: str | None,
    passthrough: list[str],
) -> None:
    project_path = str(Path(project).expanduser().resolve())
    session_name = name or "-".join(
        [
            SessionManager._slug("claude"),
            SessionManager._slug(model or "default"),
            SessionManager._slug(Path(project_path).name or "project"),
            "1",
        ]
    )
    settings = None
    if model and model != "default":
        resolved = _validate_claude_model(model)
        validate_runtime_key(resolved)
        settings = SessionManager._settings_path(session_name, "claude")
    else:
        resolved = resolve_model_spec(model or "default")
    config_dir = SessionManager._config_dir_path(session_name, "claude")
    argv = SessionManager._claude_argv(session_name, settings, passthrough)
    print(f"name: {session_name}")
    print(f"project: {project_path}")
    print("tool: claude")
    print(f"model: {resolved.canonical}")
    print(f"settings: {settings or '(default)'}")
    print(f"config_dir: {config_dir}")
    print(f"command: {SessionManager._shell_command(argv, config_dir)}")


def _validate_claude_model(model: str | None):
    try:
        return resolve_model_spec(model or "default")
    except ModelResolutionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _parse_cc_options(args: list[str]) -> tuple[CcsOptions, list[str], bool]:
    opts = CcsOptions()
    passthrough: list[str] = []
    managed = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--cc-model":
            opts.model = _take_value(args, i, arg)
            managed = True
            i += 2
        elif arg == "--cc-name":
            opts.name = _take_value(args, i, arg)
            managed = True
            i += 2
        elif arg == "--cc-project":
            opts.project = _take_value(args, i, arg)
            managed = True
            i += 2
        elif arg == "--cc-no-attach":
            opts.no_attach = True
            managed = True
            i += 1
        elif arg == "--cc-reuse":
            opts.reuse = _take_value(args, i, arg)
            managed = True
            i += 2
        elif arg == "--cc-dry-run":
            opts.dry_run = True
            managed = True
            i += 1
        elif arg.startswith("--cc-"):
            raise SystemExit(f"ccs: unknown option {arg}")
        else:
            passthrough.append(arg)
            i += 1
    return opts, passthrough, managed


def _take_value(args: list[str], index: int, flag: str) -> str:
    try:
        value = args[index + 1]
    except IndexError:
        raise SystemExit(f"ccs: {flag} requires a value") from None
    if value.startswith("--cc-"):
        raise SystemExit(f"ccs: {flag} requires a value")
    return value


def _manager() -> SessionManager:
    try:
        return SessionManager()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _exec_tool(tool: str, args: list[str]) -> None:
    try:
        result = subprocess.run([tool, *args])
    except FileNotFoundError:
        print(f"ccs: {tool} not found", file=sys.stderr)
        sys.exit(127)
    sys.exit(result.returncode)


def _print_sessions(mgr: SessionManager) -> None:
    sessions = mgr.list()
    if not sessions:
        print("No sessions. Use 'ccs claude --cc-model ds/flash' to create one.")
        return
    hdr = f"{'Name':<36} {'Tool':<8} {'Model':<20} {'Project':<20} {'PID':<8} Status"
    print(hdr)
    print("-" * len(hdr))
    for session in sessions:
        status = "running" if session.running else "stopped"
        print(
            f"{session.name:<36} {session.tool:<8} {session.model:<20} "
            f"{session.project_name:<20} {str(session.pid or ''):<8} {status}"
        )


def _print_sessions_json(mgr: SessionManager) -> None:
    print(json.dumps([session.to_json() for session in mgr.list()], indent=2))


if __name__ == "__main__":
    main()
