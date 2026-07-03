"""CLI for cc-pty."""

import sys
from pathlib import Path

from .manager import Manager


def cmd_list() -> None:
    mgr = Manager()
    sessions = mgr.list()
    if not sessions:
        print("No sessions.  Create one in the TUI (cc-pty tui).")
        return
    hdr = f"{'Name':<20} {'Project':<20} {'Model':<22}"
    sep = "─" * len(hdr)
    print(hdr)
    print(sep)
    for s in sessions:
        pname = Path(s.project).name if s.project else "?"
        print(f"{s.name:<20} {pname:<20} {s.model:<22}")


def cmd_tui() -> None:
    from .tui import PtyApp

    app = PtyApp()
    app.run()


def cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="cc-pty",
        description="Multi-session Claude Code manager (embedded PTY)",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="tui",
        choices=["tui", "list"],
        help="Command (default: tui)",
    )
    args = parser.parse_args()

    if args.command == "list":
        cmd_list()
    else:
        cmd_tui()


if __name__ == "__main__":
    cli()
