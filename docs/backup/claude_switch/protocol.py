"""Unix-socket JSON RPC helpers for ccsd."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from .store import CcsPaths


class RpcError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class CcsClient:
    def __init__(self, paths: CcsPaths | None = None) -> None:
        self.paths = paths or CcsPaths()

    def ensure_daemon(self) -> None:
        try:
            self.call("daemon.ping", {})
            return
        except (OSError, RpcError):
            pass
        self.paths.ensure()
        subprocess.Popen(
            [sys.executable, "-m", "claude_switch.daemon", "serve"],
            stdout=(self.paths.logs / "ccsd.out.log").open("ab"),
            stderr=(self.paths.logs / "ccsd.err.log").open("ab"),
            start_new_session=True,
        )
        deadline = time.time() + 5
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                self.call("daemon.ping", {})
                return
            except (OSError, RpcError) as exc:
                last_error = exc
                time.sleep(0.05)
        raise RuntimeError(f"ccsd did not start: {last_error}")

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        request = {
            "id": uuid.uuid4().hex,
            "method": method,
            "params": params or {},
        }
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(str(self.paths.socket))
            file = sock.makefile("rwb")
            file.write(json.dumps(request).encode("utf-8") + b"\n")
            file.flush()
            line = file.readline()
        if not line:
            raise RpcError("empty_response", "ccsd returned an empty response")
        response = json.loads(line.decode("utf-8"))
        if not response.get("ok"):
            error = response.get("error") or {}
            raise RpcError(str(error.get("code", "error")), str(error.get("message", "unknown error")))
        return response.get("result")


def socket_is_stale(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            sock.connect(str(path))
        return False
    except OSError:
        return True
