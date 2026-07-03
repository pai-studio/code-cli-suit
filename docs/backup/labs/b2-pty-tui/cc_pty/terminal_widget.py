"""Custom Textual widget that embeds a PTY terminal using pyte."""

import atexit
import fcntl
import os
import pty
import select
import signal
import struct
import termios
from typing import Optional

from rich.style import Style
from rich.text import Text as RichText
from textual.events import Key, Resize
from textual.strip import Strip
from textual.widget import Widget

import pyte

# ANSI 16-colour palette -> hex colours
ANSI_COLORS = [
    "#000000",  # 0  black
    "#cd0000",  # 1  red
    "#00cd00",  # 2  green
    "#cdcd00",  # 3  brown
    "#0000ee",  # 4  blue
    "#cd00cd",  # 5  magenta
    "#00cdcd",  # 6  cyan
    "#e5e5e5",  # 7  white
    "#7f7f7f",  # 8  bright black
    "#ff0000",  # 9  bright red
    "#00ff00",  # 10 bright green
    "#ffff00",  # 11 bright yellow
    "#5c5cff",  # 12 bright blue
    "#ff00ff",  # 13 bright magenta
    "#00ffff",  # 14 bright cyan
    "#ffffff",  # 15 bright white
]

# F-keys -> byte sequences (xterm)
_FKEY_MAP: dict[int, bytes] = {
    1: b"\x1bOP", 2: b"\x1bOQ", 3: b"\x1bOR", 4: b"\x1bOS",
    5: b"\x1b[15~", 6: b"\x1b[17~", 7: b"\x1b[18~", 8: b"\x1b[19~",
    9: b"\x1b[20~", 10: b"\x1b[21~", 11: b"\x1b[23~", 12: b"\x1b[24~",
}

# Ctrl+letter -> byte value
CONTROL_MAP: dict[str, int] = {
    f"ctrl+{chr(ord('a') + i)}": i + 1 for i in range(26)
}
CONTROL_MAP.update(
    {
        "ctrl+@": 0,
        "ctrl+[": 27,
        "ctrl+\\": 28,
        "ctrl+]": 29,
        "ctrl+^": 30,
        "ctrl+_": 31,
        "ctrl+backspace": 127,
    }
)

# Special keys -> byte sequences
SPECIAL_MAP: dict[str, bytes] = {
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
    "page_up": b"\x1b[5~",
    "page_down": b"\x1b[6~",
    "delete": b"\x1b[3~",
    "insert": b"\x1b[2~",
}


class TerminalWidget(Widget):
    """A Textual widget that renders a PTY-managed child process."""

    can_focus = True
    focus_on_click = True

    DEFAULT_CSS = """
    TerminalWidget {
        height: 100%;
        width: 100%;
        border: none;
        padding: 0;
    }
    TerminalWidget:focus {
        background: $boost;
    }
    """

    # Registry of all child PIDs -- cleaned up on abnormal exit
    _all_pids: "list[int]" = []
    _atexit_registered = False

    def __init__(
        self,
        command: str,
        cwd: Optional[str] = None,
        session_name: str = "",
    ) -> None:
        super().__init__()
        self._command = command
        self._cwd = cwd
        self.session_name = session_name

        self._pid: Optional[int] = None
        self._fd: Optional[int] = None
        self._screen: Optional[pyte.Screen] = None
        self._stream: Optional[pyte.Stream] = None
        self._alive = False
        self._timer: Optional[object] = None
        self._cols = 80
        self._rows = 24

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._cols = max(20, self.size.width)
        self._rows = max(5, self.size.height)
        self._screen = pyte.Screen(self._cols, self._rows)
        self._stream = pyte.Stream(self._screen)
        self._spawn()
        self._timer = self.set_interval(1 / 30, self._poll)

    def on_unmount(self) -> None:
        self._cleanup()

    def _spawn(self) -> None:
        pid, fd = pty.fork()
        if pid == 0:  # child
            try:
                # Use a full-featured terminal type so Claude Code can render cleanly.
                os.environ["TERM"] = "xterm-256color"
                os.environ.setdefault("COLORTERM", "truecolor")
                if self._cwd:
                    os.chdir(self._cwd)
                os.execvp(self._command.split()[0], self._command.split())
            except Exception as exc:
                os.write(2, f"exec failed: {exc}\r\n".encode())
                os._exit(127)
        self._pid = pid
        self._fd = fd
        self._alive = True
        self._set_pty_size(self._rows, self._cols)
        TerminalWidget._all_pids.append(pid)
        if not TerminalWidget._atexit_registered:
            atexit.register(TerminalWidget._kill_all_orphans)
            TerminalWidget._atexit_registered = True

    # ------------------------------------------------------------------
    # PTY size
    # ------------------------------------------------------------------

    def _set_pty_size(self, rows: int, cols: int) -> None:
        """Set kernel PTY window size via TIOCSWINSZ."""
        if self._fd is None:
            return
        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    @staticmethod
    def _kill_all_orphans() -> None:
        for pid in TerminalWidget._all_pids:
            try:
                os.kill(pid, signal.SIGHUP)
                os.waitpid(pid, 0)
            except (OSError, ChildProcessError):
                pass

    def _cleanup(self) -> None:
        self._alive = False
        if self._timer is not None:
            try:
                self._timer.stop()
            except Exception:
                pass
            self._timer = None
        if self._pid is not None:
            try:
                os.kill(self._pid, signal.SIGHUP)
                os.waitpid(self._pid, 0)
            except (OSError, ChildProcessError):
                pass
            self._pid = None
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def _mark_exited(self) -> None:
        """Called when the child process exits -- immediate reap + close."""
        self._alive = False
        if self._pid is not None:
            try:
                os.waitpid(self._pid, os.WNOHANG)
            except (OSError, ChildProcessError):
                pass
            self._pid = None
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        self.refresh()

    # ------------------------------------------------------------------
    # PTY polling
    # ------------------------------------------------------------------

    def _poll(self) -> None:
        if not self._alive or self._fd is None:
            self.refresh()
            return
        try:
            r, _, _ = select.select([self._fd], [], [], 0)
            if not r:
                return
            data = os.read(self._fd, 65536)
            if data:
                self._stream.feed(data.decode("utf-8", errors="replace"))
                self.refresh()
            else:
                self._mark_exited()
        except (OSError, ValueError):
            self._mark_exited()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render_line(self, y: int) -> Strip:
        if self._screen is None or y >= self._screen.lines:
            return Strip.blank(self.size.width, self.visual_style.rich_style)

        line = self._screen.buffer[y]
        # Build as (char, style) segments so we can modify a single cell for the cursor
        segments: list[tuple[str, Style]] = []

        for x in range(self._screen.columns):
            ch = line.get(x, self._screen.default_char)
            style = self._char_style(ch)
            segments.append((ch.data or " ", style))

        # Cursor on this line
        if y == self._screen.cursor.y and self._alive:
            cx = self._screen.cursor.x
            if 0 <= cx < len(segments):
                ch, _ = segments[cx]
                if ch.strip():
                    segments[cx] = (ch, Style(reverse=True))
                else:
                    segments[cx] = (" ", Style(color="white", bgcolor="white"))

        text = RichText()
        for ch, style in segments:
            text.append(ch, style)
        return Strip(text.render(self.app.console))

    # ------------------------------------------------------------------
    # Colour helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_color(c) -> "str | None":
        """Convert pyte colour (int 0-15 or hex str) to a hex string."""
        if isinstance(c, int):
            if 0 <= c < 16:
                return ANSI_COLORS[c]
            return None  # 256-color palette -- not supported
        if isinstance(c, str) and c.startswith("#"):
            return c  # true-color hex
        return None

    @staticmethod
    def _char_style(ch: "pyte.screens.Char") -> Style:
        """Convert a pyte Char to a rich Style."""
        attrs: dict = {}
        if ch.bold:
            attrs["bold"] = True
        if ch.italics:
            attrs["italic"] = True
        if ch.underscore:
            attrs["underline"] = True
        if ch.blink:
            attrs["blink"] = True
        if ch.strikethrough:
            attrs["strikethrough"] = True

        fg = TerminalWidget._resolve_color(ch.fg)
        bg = TerminalWidget._resolve_color(ch.bg)

        if ch.reverse:
            attrs["color"] = bg or "white"
            attrs["bgcolor"] = fg or "black"
        else:
            if fg:
                attrs["color"] = fg
            if bg:
                attrs["bgcolor"] = bg

        return Style(**attrs)

    # ------------------------------------------------------------------
    # Keyboard input  ->  PTY
    # ------------------------------------------------------------------

    def on_key(self, event: Key) -> None:
        if not self._alive or self._fd is None:
            return
        data = self._key_to_bytes(event)
        if data:
            try:
                os.write(self._fd, data)
            except OSError:
                pass
            event.prevent_default()

    @staticmethod
    def _key_to_bytes(event: Key) -> bytes:
        key = event.key
        char = event.character

        # Ctrl+letter
        if key in CONTROL_MAP:
            return bytes([CONTROL_MAP[key]])

        # Named special keys
        if key in SPECIAL_MAP:
            return SPECIAL_MAP[key]

        # F-keys
        if key.startswith("f") and len(key) <= 3:
            try:
                n = int(key[1:])
            except ValueError:
                pass
            else:
                if 1 <= n <= 12:
                    return _FKEY_MAP[n]

        # Printable character
        if char is not None:
            return char.encode("utf-8")
        if len(key) == 1:
            return key.encode("utf-8")

        return b""

    # ------------------------------------------------------------------
    # Resize
    # ------------------------------------------------------------------

    def on_resize(self, event: Resize) -> None:
        cols = max(20, event.size.width)
        rows = max(5, event.size.height)
        if self._screen and (cols != self._cols or rows != self._rows):
            self._cols = cols
            self._rows = rows
            self._screen.resize(rows, cols)
            self._set_pty_size(rows, cols)
            if self._pid is not None:
                try:
                    os.kill(self._pid, signal.SIGWINCH)
                except OSError:
                    pass
