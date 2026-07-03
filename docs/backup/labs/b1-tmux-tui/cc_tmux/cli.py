"""CLI for cc-tmux."""

import sys

from .manager import Manager


def _manager() -> Manager:
    try:
        return Manager()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_list():
    mgr = _manager()
    sessions = mgr.list()
    if not sessions:
        print("No sessions.  Use 'cc-tmux new' to create one.")
        return
    hdr = f"{'Name':<20} {'Project':<20} {'Model':<22} {'PID':<8} Status"
    sep = "─" * len(hdr)
    print(hdr)
    print(sep)
    for s in sessions:
        status = "● running" if s.running else "○ stopped"
        print(
            f"{s.name:<20} {s.project_name:<20} {s.model:<22} "
            f"{str(s.pid or ''):<8} {status}"
        )


def cmd_new(name: str, project: str, model: str | None):
    mgr = _manager()
    try:
        s = mgr.new(name, project, model)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Created session '{s.name}'  (pid {s.pid})")
    print(f"  Project: {s.project}")
    print(f"  Model:   {s.model}")
    print(f"  tmux:    cc-tmux window #{s.index}")
    print("Run: cc-tmux attach <name> to connect")


def cmd_attach(name: str):
    mgr = _manager()
    try:
        mgr.attach(name)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_kill(name: str):
    mgr = _manager()
    try:
        mgr.kill(name)
        print(f"Killed session '{name}'")
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_set_model(name: str, model: str):
    mgr = _manager()
    try:
        mgr.set_model(name, model)
        print(f"Restarted session '{name}' with model {model}")
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_rename(old: str, new: str):
    mgr = _manager()
    try:
        mgr.rename(old, new)
        print(f"Renamed '{old}' → '{new}'")
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_tui():
    from .tui import TmuxApp

    app = TmuxApp()
    result = app.run()
    if isinstance(result, tuple) and len(result) == 2:
        name, action = result
        if action == "attach":
            try:
                Manager().attach(name)
            except RuntimeError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                sys.exit(1)


def cli():
    import argparse

    parser = argparse.ArgumentParser(
        prog="cc-tmux",
        description="Multi-session Claude Code manager (tmux backend)",
    )
    sub = parser.add_subparsers(dest="command", help="sub-command")

    # list
    sub.add_parser("list", help="List all sessions")

    # new
    p_new = sub.add_parser("new", help="Create a new session")
    p_new.add_argument("name", help="Session name")
    p_new.add_argument("-p", "--project", default=".", help="Project directory")
    p_new.add_argument(
        "-m",
        "--model",
        "--cc-model",
        default=None,
        help="claude-switch profile/model (e.g. sonnet, deepseek-flash)",
    )

    # attach
    p_attach = sub.add_parser("attach", help="Attach to a session")
    p_attach.add_argument("name", help="Session name")

    # kill
    p_kill = sub.add_parser("kill", help="Kill a session")
    p_kill.add_argument("name", help="Session name")

    # model
    p_model = sub.add_parser("model", help="Restart a session with a model")
    p_model.add_argument("name", help="Session name")
    p_model.add_argument("model", help="claude-switch profile/model (e.g. sonnet)")

    # rename
    p_rename = sub.add_parser("rename", help="Rename a session")
    p_rename.add_argument("name", help="Current session name")
    p_rename.add_argument("new_name", help="New session name")

    # tui
    sub.add_parser("tui", help="Launch TUI dashboard")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list()
    elif args.command == "new":
        cmd_new(args.name, args.project, args.model)
    elif args.command == "attach":
        cmd_attach(args.name)
    elif args.command == "kill":
        cmd_kill(args.name)
    elif args.command == "model":
        cmd_set_model(args.name, args.model)
    elif args.command == "rename":
        cmd_rename(args.name, args.new_name)
    elif args.command == "tui":
        cmd_tui()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    cli()
