# more complete / pyte , pty terminal version.. although scrolling is buggy
import collections
import fcntl
import os
import pty
import re
import struct
import termios
import threading
from functools import partial

import lib.display.glyphs as glyphs
import pyte
from lib.display.window import Executable  # Using your provided Executable
# ... (other imports are the same) ...
# from lib.display import glyphs # Assuming this is your glyphs library
from pyte.screens import Char
from rich.color import ColorParseError
from rich.style import Style
from rich.text import Text
from textual import events, log
from textual.color import Color
from textual.message import Message
from textual.reactive import reactive
from textual.theme import Theme  # Import the Theme object
from textual.widget import Widget

# A more comprehensive regex to strip unsupported sequences.
# 1. \x1b\[\?[\d;]+[a-zA-Z]  ->  Matches private mode sequences like CSI-u (`...u`) and others (`...h`, `...l`).
# 2. \x1b\][^\x07]*(\x07|\x1b\\) -> Matches Operating System Commands (OSC), e.g., for setting window titles.
RE_STRIP_UNSUPPORTED = re.compile(
    r"\x1b\[\?[\d;]+[a-zA-Z]"                  # DEC private mode (e.g., ?25h)
    r"|\x1b\][^\x07]*(\x07|\x1b\\)"            # OSC sequences (e.g., set window title)
    r"|\x1b\[=?\d+(?:;\d+)*u"                  # ONLY CSI-u sequences like \x1b[=5u
)

PYTE_TO_CSS_VAR_NAME = {
    "black": "surface", "red": "error", "green": "success", "brown": "warning",
    "blue": "primary", "magenta": "accent", "cyan": "secondary", "white": "foreground",
    "brightblack": "foreground-muted", "brightred": "error-lighten-2", "brightgreen": "success-lighten-2",
    "brightyellow": "warning-lighten-2", "brightblue": "primary-lighten-2", "brightmagenta": "accent-lighten-2",
    "brightcyan": "secondary-lighten-2", "brightwhite": "foreground",
}

KEY_TRANSLATIONS = {
    "up": b"\x1b[A", "down": b"\x1b[B", "right": b"\x1b[C", "left": b"\x1b[D",
    "home": b"\x1b[H", "end": b"\x1b[F", "pageup": b"\x1b[5~", "pagedown": b"\x1b[6~",
    "delete": b"\x1b[3~", "insert": b"\x1b[2~", "ctrl+c": b"\x03", "ctrl+d": b"\x04",
}


RE_IS_CLEAR_SCREEN = re.compile(r"\x1b\[[23]J")


def _pyte_to_rich_style(char: Char, color_cache: dict[str, str]) -> Style:
    """A standalone helper function for converting pyte.Char to rich.Style."""
    def get_color(pyte_color: str, is_bg: bool = False) -> str:
        if pyte_color == "default": return color_cache.get("default_bg" if is_bg else "default_fg", "")
        cached = color_cache.get(pyte_color)
        if cached: return cached
        if ";" in pyte_color: return f"rgb({','.join(pyte_color.split(';'))})"
        if len(pyte_color) == 6: return f"#{pyte_color}"
        return pyte_color
    try:
        color = get_color(char.fg)
        bgcolor = get_color(char.bg, is_bg=True)
        return Style(
            color=color, bgcolor=bgcolor, bold=char.bold, italic=char.italics,
            underline=char.underscore, strike=char.strikethrough, reverse=char.reverse,
        )
    except (ColorParseError, KeyError): return Style.null()


class HistoryScreen(pyte.Screen):
    """A pyte.Screen subclass that captures scrolled-off lines into a history buffer."""
    def __init__(self, columns, lines, history_size, color_cache):
        super().__init__(columns, lines)
        self.history = collections.deque(maxlen=history_size)
        self._color_cache = color_cache

    def scroll_up(self, count):
        """Called when lines are scrolled off the top of the screen."""
        for _ in range(count):
            if 0 in self.buffer:
                top_line = self.buffer[0]
                rendered_line = self._render_pyte_line(top_line)
                self.history.append(rendered_line)
        super().scroll_up(count)

    def _render_pyte_line(self, pyte_line: dict[int, Char]) -> Text:
        """Renders a single line from the pyte buffer into a Rich Text object."""
        line_text = Text(no_wrap=True)
        last_style: Style | None = None
        current_run = ""
        for x in range(self.columns):
            char = pyte_line.get(x, self.default_char)
            style = _pyte_to_rich_style(char, self._color_cache)
            if style != last_style:
                if current_run: line_text.append(current_run, last_style)
                current_run, last_style = char.data, style
            else:
                current_run += char.data
        if current_run: line_text.append(current_run, last_style)
        return line_text


class Terminal(Widget, can_focus=True):
    DEFAULT_CSS = """
    Terminal {
        background: $surface;
    }
    """
    scroll_offset = reactive(0, layout=True)

    def __init__(self, *, shell_mode: str = "full", scrollback: int = 10000, **kwargs):
        super().__init__(**kwargs)
        self.shell_mode = shell_mode
        self._term_width, self._term_height = 80, 24
        self._color_cache: dict[str, str] = {}
        self.decode_buffer = b""

        self.pyte_screen = HistoryScreen(self._term_width, self._term_height, scrollback, self._color_cache)
        self.pyte_stream = pyte.Stream(self.pyte_screen)
        self._last_captured_screen: list[str] = []
        self._last_screen_hash = ""

        self.master_fd: int | None = None
        self.child_pid: int | None = None
        self.reader_thread: threading.Thread | None = None

    def on_resize(self, event: events.Resize) -> None:
        new_width, new_height = event.size.width, event.size.height

        self._capture_history()

        self._term_width, self._term_height = new_width, new_height
        self.scroll_offset = 0
        self.pyte_screen.resize(lines=new_height, columns=new_width)

        if self.master_fd:
            size_data = struct.pack("HHHH", new_height, new_width, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, size_data)

        self.pyte_screen.dirty.update(range(new_height))
        self.refresh(layout=True)

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        max_scroll = max(0, len(self.pyte_screen.history) + self.pyte_screen.lines - self._term_height)
        self.scroll_offset = min(max_scroll, self.scroll_offset + 3)
        self.refresh(layout=True)

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self.scroll_offset = max(0, self.scroll_offset - 3)
        self.refresh(layout=True)

    def _capture_history(self):
        current_lines = [
            self.pyte_screen._render_pyte_line(self.pyte_screen.buffer.get(y, {})).plain
            for y in range(self._term_height)
        ]

        screen_hash = hash("\n".join(current_lines))
        if screen_hash == self._last_screen_hash:
            return

        self._last_screen_hash = screen_hash

        log.info("Captured history:")
        for line in current_lines:
            log.debug(f"> {line!r}")

        self._last_captured_screen = current_lines[:]

        for line in current_lines:
            if line.strip():
                self.pyte_screen.history.append(Text(line))

    def _write_to_pyte(self, data: bytes) -> None:
        data = self.decode_buffer + data
        try:
            text_data = data.decode("utf-8", "surrogatepass")
            self.decode_buffer = b""
        except UnicodeDecodeError as e:
            text_data = data[:e.start].decode("utf-8", "surrogatepass")
            self.decode_buffer = data[e.start:]

        filtered_data = RE_STRIP_UNSUPPORTED.sub("", text_data)
        if filtered_data:
            self.pyte_stream.feed(filtered_data)
            self._capture_history()
            self.refresh()

        if self.scroll_offset > 0:
            self.scroll_offset = 0  # snap back to live view when new data arrives

    def _start_pty_process(self) -> None:
        pid, master_fd = pty.fork()
        if pid == 0:
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            if self.shell_mode == "safe":
                shell_path = "/bin/bash"
                argv = [shell_path, "--norc", "--noprofile"]
                try:
                    os.execvpe(shell_path, argv, env)
                except FileNotFoundError:
                    os.execvpe("/bin/sh", ["/bin/sh"], env)
            else:
                shell_path = env.get("SHELL", "/bin/bash")
                argv = [shell_path]
                os.execvpe(shell_path, argv, env)
        else:
            self.child_pid, self.master_fd = pid, master_fd
            self.reader_thread = threading.Thread(target=self._read_from_pty, daemon=True)
            self.reader_thread.start()

    def on_mount(self) -> None:
        self._populate_color_cache()
        self.on_resize(events.Resize(self.size, self.size))
        self._start_pty_process()

    def _populate_color_cache(self) -> None:
        if not self.is_mounted:
            return
        try:
            css_variables = self.app.get_css_variables()
            for pyte_color, var_name in PYTE_TO_CSS_VAR_NAME.items():
                if var_name in css_variables:
                    self._color_cache[pyte_color] = Color.parse(css_variables[var_name]).hex
                else:
                    self._color_cache[pyte_color] = "#ff00ff"  # fallback magenta
            self._color_cache["default_fg"] = Color.parse(css_variables["foreground"]).hex
            self._color_cache["default_bg"] = Color.parse(css_variables["background"]).hex
        except Exception as e:
            log.warning(f"Could not populate terminal color cache: {e}")

    def on_styles_updated(self, message: Message) -> None:
        self._populate_color_cache()
        self.pyte_screen.dirty.update(range(self.pyte_screen.lines))
        self.refresh()

    def render(self) -> Text:
        if not self.is_mounted:
            return Text("")

        active_lines = [
            self.pyte_screen._render_pyte_line(self.pyte_screen.buffer.get(y, {}))
            for y in range(self._term_height)
        ]

        full_buffer = list(self.pyte_screen.history) + active_lines
        max_scroll = max(0, len(full_buffer) - self._term_height)
        self.scroll_offset = min(self.scroll_offset, max_scroll)

        if self.scroll_offset > 0:
            start = max(0, len(full_buffer) - self._term_height - self.scroll_offset)
            end = start + self._term_height
            display_lines = full_buffer[start:end]
        else:
            display_lines = full_buffer[-self._term_height:]

        is_cursor_visible = self.has_focus and self.scroll_offset == 0
        if is_cursor_visible:
            cursor = self.pyte_screen.cursor
            y, x = cursor.y, cursor.x
            if 0 <= y < len(display_lines):
                line = display_lines[y]
                if x < len(line.plain):
                    line.stylize_before("reverse", start=x, end=x + 1)
                else:
                    line.append(" ", style="reverse")

        while len(display_lines) < self._term_height:
            display_lines.append(Text(""))

        return Text("\n").join(display_lines)

    def on_unmount(self) -> None:
        if self.child_pid:
            try:
                os.kill(self.child_pid, 9)
            except ProcessLookupError:
                pass
        if self.master_fd:
            os.close(self.master_fd)

    def on_key(self, event: events.Key) -> None:
        if self.master_fd is None:
            return
        if event.key in KEY_TRANSLATIONS:
            os.write(self.master_fd, KEY_TRANSLATIONS[event.key])
        elif event.character:
            os.write(self.master_fd, event.character.encode())
        elif event.key == "pageup":
            max_scroll = max(0, len(self.pyte_screen.history) + self.pyte_screen.lines - self._term_height)
            self.scroll_offset = min(self.scroll_offset + self._term_height // 2, max_scroll)
            self.refresh()
        elif event.key == "pagedown":
            self.scroll_offset = max(self.scroll_offset - self._term_height // 2, 0)
            self.refresh()

    def _read_from_pty(self) -> None:
        while self.master_fd is not None:
            try:
                data = os.read(self.master_fd, 1024)
                if not data:
                    break
                self.app.call_from_thread(self._write_to_pyte, data)
            except OSError:
                break


class Dustty(Executable):
    APP_NAME = "Patty"
    @property
    def APP_ICON(self): return glyphs.icons.get("terminal", "?")

    MAIN_WIDGET = Terminal
