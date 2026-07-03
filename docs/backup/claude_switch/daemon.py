"""Daemon process for PTY-backed ccs sessions."""

from __future__ import annotations

import fcntl
import json
import os
import pty
import select
import signal
import socket
import struct
import sys
import termios
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyte

from .adapters import get_adapter
from .protocol import socket_is_stale
from .store import CcsPaths, SessionRecord, SessionStore, now_ts


MAX_SCROLLBACK = 4000


@dataclass
class RuntimeSession:
    record: SessionRecord
    fd: int
    screen: pyte.HistoryScreen
    stream: pyte.Stream
    buffer: bytearray = field(default_factory=bytearray)
    lock: threading.Lock = field(default_factory=threading.Lock)
    rows: int = 30
    cols: int = 120


class CcsDaemon:
    def __init__(self, paths: CcsPaths | None = None) -> None:
        self.paths = paths or CcsPaths()
        self.store = SessionStore(self.paths)
        self.sessions: dict[str, RuntimeSession] = {}
        self._stop = threading.Event()

    def serve_forever(self) -> None:
        self.paths.ensure()
        if socket_is_stale(self.paths.socket):
            self.paths.socket.unlink(missing_ok=True)
        if self.paths.socket.exists():
            raise RuntimeError(f"ccsd socket already exists: {self.paths.socket}")
        self.paths.pid.write_text(f"{os.getpid()}\n")
        os.umask(0o077)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.paths.socket))
        server.listen(32)
        threading.Thread(target=self._poll_loop, daemon=True).start()
        try:
            while not self._stop.is_set():
                conn, _ = server.accept()
                threading.Thread(target=self._handle_conn, args=(conn,), daemon=True).start()
        finally:
            server.close()
            self.paths.socket.unlink(missing_ok=True)

    def _handle_conn(self, conn: socket.socket) -> None:
        with conn:
            file = conn.makefile("rwb")
            line = file.readline()
            if not line:
                return
            try:
                request = json.loads(line.decode("utf-8"))
                result = self._dispatch(str(request.get("method")), request.get("params") or {})
                response = {"id": request.get("id"), "ok": True, "result": result}
            except Exception as exc:
                response = {
                    "id": None,
                    "ok": False,
                    "error": {"code": exc.__class__.__name__, "message": str(exc)},
                }
            file.write(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")
            file.flush()

    def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "daemon.ping":
            return {"pid": os.getpid(), "version": 1}
        if method == "daemon.shutdown":
            threading.Timer(0.05, self._shutdown_now).start()
            return {"ok": True}
        if method == "session.list":
            return [self._record_json(record) for record in self._records()]
        if method == "session.create":
            return self.create_session(params).to_json()
        if method == "session.kill":
            self.kill_session(str(params["name"]))
            return {"ok": True}
        if method == "session.restart":
            return self.restart_session(str(params["name"])).to_json()
        if method == "session.switch_model":
            return self.switch_model(str(params["name"]), str(params["model"])).to_json()
        if method == "session.activate":
            return self.activate(str(params["name"])).to_json()
        if method == "terminal.snapshot":
            return self.snapshot(str(params["name"]), int(params.get("lines", 200)))
        if method == "terminal.input":
            self.write_input(str(params["name"]), str(params.get("data", "")).encode("utf-8"))
            return {"ok": True}
        if method == "terminal.resize":
            self.resize(str(params["name"]), int(params["rows"]), int(params["cols"]))
            return {"ok": True}
        raise ValueError(f"unknown method '{method}'")

    def _shutdown_now(self) -> None:
        self.paths.socket.unlink(missing_ok=True)
        os._exit(0)

    def create_session(self, params: dict[str, Any]) -> SessionRecord:
        tool = str(params.get("tool") or "claude")
        model = str(params.get("model") or "default")
        project = str(params.get("project") or ".")
        argv = [str(item) for item in params.get("argv", [])]
        name = params.get("name")
        record = self.store.make_record(
            tool=tool,
            model=model,
            project=project,
            argv=argv,
            name=str(name) if name else None,
        )
        self._spawn(record)
        return record

    def kill_session(self, name: str) -> None:
        record = self._get_record(name)
        runtime = self.sessions.pop(record.id, None)
        if runtime is not None:
            self._terminate(runtime)
        record.status = "exited"
        record.updated_at = now_ts()
        self.store.delete(record.id)

    def restart_session(self, name: str) -> SessionRecord:
        record = self._get_record(name)
        runtime = self.sessions.pop(record.id, None)
        if runtime is not None:
            self._terminate(runtime)
        record.status = "starting"
        record.pid = None
        record.exit_code = None
        record.updated_at = now_ts()
        self.store.upsert(record)
        self._spawn(record)
        return record

    def switch_model(self, name: str, model: str) -> SessionRecord:
        record = self._get_record(name)
        record.model = model
        record.updated_at = now_ts()
        self.store.upsert(record)
        return self.restart_session(record.id)

    def activate(self, name: str) -> SessionRecord:
        record = self._get_record(name)
        record.last_active_at = now_ts()
        self.store.upsert(record)
        return record

    def snapshot(self, name: str, lines: int) -> dict[str, Any]:
        record = self._get_record(name)
        runtime = self.sessions.get(record.id)
        data = b""
        rows = 30
        cols = 120
        if runtime is not None:
            with runtime.lock:
                data = bytes(runtime.buffer)
                rows = runtime.rows
                cols = runtime.cols
        text = _clean_ansi(data.decode("utf-8", errors="replace"))
        if runtime is not None:
            with runtime.lock:
                rows_text = _screen_lines(runtime.screen, max(1, lines))
        else:
            text = _clean_ansi(data.decode("utf-8", errors="replace"))
            rows_text = text.splitlines()[-max(1, lines) :]
        return {
            "session": self._record_json(record),
            "rows": rows,
            "cols": cols,
            "lines": rows_text,
        }

    def write_input(self, name: str, data: bytes) -> None:
        record = self._get_record(name)
        runtime = self.sessions.get(record.id)
        if runtime is None:
            raise RuntimeError(f"session '{name}' is not running")
        os.write(runtime.fd, data)

    def resize(self, name: str, rows: int, cols: int) -> None:
        record = self._get_record(name)
        runtime = self.sessions.get(record.id)
        if runtime is None:
            return
        runtime.rows = max(5, rows)
        runtime.cols = max(20, cols)
        with runtime.lock:
            runtime.screen.resize(runtime.rows, runtime.cols)
        winsize = struct.pack("HHHH", runtime.rows, runtime.cols, 0, 0)
        try:
            fcntl.ioctl(runtime.fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    def _spawn(self, record: SessionRecord) -> None:
        adapter = get_adapter(record.tool)
        prepared = adapter.prepare(record, self.paths)
        pid, fd = pty.fork()
        if pid == 0:
            try:
                env = os.environ.copy()
                env.update(prepared.env)
                env.update(record.env)
                env.setdefault("TERM", "xterm-256color")
                env.setdefault("COLORTERM", "truecolor")
                os.chdir(prepared.cwd)
                os.execvpe(prepared.command[0], prepared.command, env)
            except Exception as exc:
                os.write(2, f"exec failed: {exc}\r\n".encode("utf-8", errors="replace"))
                os._exit(127)
        record.pid = pid
        record.status = "running"
        record.updated_at = now_ts()
        self.store.upsert(record)
        screen = pyte.HistoryScreen(120, 30, history=MAX_SCROLLBACK)
        self.sessions[record.id] = RuntimeSession(record=record, fd=fd, screen=screen, stream=pyte.Stream(screen))

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            runtimes = list(self.sessions.values())
            if not runtimes:
                time.sleep(0.05)
                continue
            fds = [runtime.fd for runtime in runtimes]
            try:
                readable, _, _ = select.select(fds, [], [], 0.05)
            except OSError:
                continue
            for runtime in runtimes:
                if runtime.fd not in readable:
                    continue
                try:
                    chunk = os.read(runtime.fd, 65536)
                except OSError:
                    chunk = b""
                if chunk:
                    with runtime.lock:
                        runtime.stream.feed(chunk.decode("utf-8", errors="replace"))
                        runtime.buffer.extend(chunk)
                        if len(runtime.buffer) > MAX_SCROLLBACK * 160:
                            del runtime.buffer[: len(runtime.buffer) - MAX_SCROLLBACK * 160]
                else:
                    self._mark_exited(runtime)

    def _mark_exited(self, runtime: RuntimeSession) -> None:
        self.sessions.pop(runtime.record.id, None)
        try:
            _, status = os.waitpid(runtime.record.pid or -1, os.WNOHANG)
            runtime.record.exit_code = os.waitstatus_to_exitcode(status) if status else None
        except (OSError, ChildProcessError):
            runtime.record.exit_code = None
        try:
            os.close(runtime.fd)
        except OSError:
            pass
        runtime.record.status = "exited"
        runtime.record.updated_at = now_ts()
        self.store.upsert(runtime.record)

    def _terminate(self, runtime: RuntimeSession) -> None:
        if runtime.record.pid:
            try:
                os.kill(runtime.record.pid, signal.SIGHUP)
            except OSError:
                pass
            try:
                os.waitpid(runtime.record.pid, 0)
            except (OSError, ChildProcessError):
                pass
        try:
            os.close(runtime.fd)
        except OSError:
            pass

    def _records(self) -> list[SessionRecord]:
        records = self.store.list()
        runtime_ids = set(self.sessions)
        for record in records:
            if record.id not in runtime_ids and record.status in {"starting", "running"}:
                record.status = "exited"
        return sorted(records, key=lambda r: r.last_active_at or r.created_at)

    def _get_record(self, name: str) -> SessionRecord:
        record = self.store.get(name)
        if record is None:
            raise RuntimeError(f"session '{name}' not found")
        return record

    def _record_json(self, record: SessionRecord) -> dict:
        data = record.to_json()
        data["running"] = record.id in self.sessions and record.status == "running"
        data["project_name"] = Path(record.project).name if record.project else "?"
        return data


def _clean_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text).replace("\r\n", "\n").replace("\r", "\n")


def _screen_lines(screen: pyte.HistoryScreen, lines: int) -> list[str]:
    history = [_line_from_cells(row, screen.columns) for row in screen.history.top]
    visible = [row.rstrip() for row in screen.display]
    combined = history + visible
    return combined[-lines:]


def _line_from_cells(cells: dict[int, object], columns: int) -> str:
    chars = [" "] * columns
    for index, char in cells.items():
        if 0 <= index < columns:
            chars[index] = getattr(char, "data", " ")
    return "".join(chars).rstrip()


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["serve"]:
        print("usage: python -m claude_switch.daemon serve", file=sys.stderr)
        raise SystemExit(2)
    CcsDaemon().serve_forever()


if __name__ == "__main__":
    main()
