# a usable terminal emulator that works with textual
# supports:

# training data(?): pyte api reference, mitosch textual-terminal, pyte terminal example, gate one terminal documentation
import fcntl
import os
import pty
import re
import struct
import termios
import threading
from collections import deque
from typing import Optional, Tuple

import pyte
from lib.display.window import Executable
from pyte import modes as pyte_modes
from pyte.screens import Char, Screen
from rich.color import ColorParseError
from rich.style import Style
from rich.text import Text
from textual import events
from textual.reactive import reactive
from textual.widget import Widget

ENTER_ALT_SCREEN = b"\x1b[?1049h"
EXIT_ALT_SCREEN = b"\x1b[?1049l"

BASE_KEY_CODES = {
    # arrows
    "up": "A", "down": "B", "right": "C", "left": "D",
    # home/end
    "home": "H", "end": "F",
    # page/insert/delete use tilde style
    "pageup": "5~", "pagedown": "6~",
    "insert": "2~", "delete": "3~",
    # function keys F1-F4 as SS3 (P/Q/R/S), F5+ as tilde codes
    "f1": "P", "f2": "Q", "f3": "R", "f4": "S",
    "f5": "15~", "f6": "17~", "f7": "18~", "f8": "19~",
    "f9": "20~", "f10": "21~", "f11": "23~", "f12": "24~",
    # extended function keys (common mappings)
    "f13": "25~", "f14": "26~", "f15": "28~", "f16": "29~",
    "f17": "31~", "f18": "32~", "f19": "33~", "f20": "34~",
    "f21": "35~", "f22": "36~", "f23": "37~", "f24": "38~",
    # keypad (common "application" / SS3 forms are different; we provide numeric keypad placeholders)
    "kp_0": "Op", "kp_1": "Oq", "kp_2": "Or", "kp_3": "Os", "kp_4": "Ot",
    "kp_5": "Ou", "kp_6": "Ov", "kp_7": "Ow", "kp_8": "Ox", "kp_9": "Oy",
    "kp_enter": "M",
}
# --- NEW: Raw DEC Private Mode sequences for mouse handling ---
MOUSE_PROTOCOLS = {
    # Enable/Disable DECSET/DECRST sequences
    b"\x1b[?1000h": ("normal_mouse", True),
    b"\x1b[?1000l": ("normal_mouse", False),
    b"\x1b[?1002h": ("button_event_mouse", True),
    b"\x1b[?1002l": ("button_event_mouse", False),
    b"\x1b[?1003h": ("any_event_mouse", True),
    b"\x1b[?1003l": ("any_event_mouse", False),
    b"\x1b[?1006h": ("sgr_mouse", True),
    b"\x1b[?1006l": ("sgr_mouse", False),
}
KEY_TRANSLATIONS = {
    # simple
    "enter": b"\r", "return": b"\r",
    "backspace": b"\x7f", "tab": b"\t", "escape": b"\x1b",
    "shift+tab": b"\x1b[Z",

    # arrows & navigation
    "up": b"\x1b[A", "down": b"\x1b[B", "right": b"\x1b[C", "left": b"\x1b[D",
    "home": b"\x1b[H", "end": b"\x1b[F", "pageup": b"\x1b[5~", "pagedown": b"\x1b[6~",
    "insert": b"\x1b[2~", "delete": b"\x1b[3~",

    # function keys
    "f1": b"\x1bOP", "f2": b"\x1bOQ", "f3": b"\x1bOR", "f4": b"\x1bOS",
    "f5": b"\x1b[15~", "f6": b"\x1b[17~", "f7": b"\x1b[18~", "f8": b"\x1b[19~",
    "f9": b"\x1b[20~", "f10": b"\x1b[21~", "f11": b"\x1b[23~", "f12": b"\x1b[24~",

    # explicit Ctrl combos
    "ctrl+space": b"\x00",
    "ctrl+@": b"\x00",
    "ctrl+a": b"\x01", "ctrl+b": b"\x02", "ctrl+c": b"\x03", "ctrl+d": b"\x04",
    "ctrl+e": b"\x05", "ctrl+f": b"\x06", "ctrl+g": b"\x07", "ctrl+h": b"\x08",
    "ctrl+i": b"\t",   "ctrl+j": b"\n",   "ctrl+k": b"\x0b", "ctrl+l": b"\x0c",
    "ctrl+m": b"\r",   "ctrl+n": b"\x0e", "ctrl+o": b"\x0f", "ctrl+p": b"\x10",
    "ctrl+q": b"\x11", "ctrl+r": b"\x12", "ctrl+s": b"\x13", "ctrl+t": b"\x14",
    "ctrl+u": b"\x15", "ctrl+v": b"\x16", "ctrl+w": b"\x17", "ctrl+x": b"\x18",
    "ctrl+y": b"\x19", "ctrl+z": b"\x1a",
    "ctrl+backspace": b"\x08",
    "ctrl+\\": b"\x1c", "ctrl+]": b"\x1d", "ctrl+^": b"\x1e",
}
# --- Regex to sanitize private SGR sequences that pyte misinterprets for some reason?---
PRV_SGR_RE = re.compile(r'\x1b\[[>?][0-9;]*m')
# Regex for DCS (Device Control String) sequences ---
DCS_RE = re.compile(r'\x1bP.*?\x1b\\', re.DOTALL)
OSC_RE = re.compile(r'\x1b\][^\x07\x1b]*?(?:\x07|\x1b\\)')
APC_RE = re.compile(r'\x1b_.*?\x1b\\', re.DOTALL)
PM_RE = re.compile(r'\x1b\^.*?\x1b\\', re.DOTALL)

_HEX_CHARS = "0123456789abcdefABCDEF"

# Filter priority binds. These keys will be passed up to the parent application.
GUI_KEY_BINDINGS = {
    "ctrl+q",
    "alt+tab",
    "alt+q",
}


class CustomHistoryScreen(Screen):
    def __init__(self, columns, lines, history: deque, terminal_widget: "Terminal"):
        self.history = history
        self.terminal_widget = terminal_widget
        super().__init__(columns, lines)

    def index(self):
        if not self.terminal_widget.in_alternate_screen and self.cursor.y == self.lines - 1:
            self.history.append(self.buffer[0].copy())
        super().index()

    def report_device_attributes(self, *args, **kwargs):
        """
        Called by pyte when the underlying app sends a DA request.
        We respond by telling the app we are a VT102 terminal.
        """
        print("[CustomHistoryScreen.report_device_attributes] Received DA request.")
        # VT102 response: `ESC [ ? 6 c`
        response = b"\x1b[?6c"
        self.terminal_widget.write_to_pty(response)
        # Call the original method (which is a no-op but good practice)
        super().report_device_attributes(*args, **kwargs)


def _pyte_to_rich_style(char: Char) -> Style:
    """A safer version of the style converter with a BCE workaround."""
    try:
        fg_is_hex = len(char.fg) == 6 and all(c in _HEX_CHARS for c in char.fg)
        bg_is_hex = len(char.bg) == 6 and all(c in _HEX_CHARS for c in char.bg)
        color = f"#{char.fg}" if fg_is_hex else char.fg
        bgcolor = f"#{char.bg}" if bg_is_hex else char.bg

        # Detects an erased "blank" cell and avoids applying text attributes to it.
        is_blank_space = char.data == ' '
        # Check against None as well, as pyte might use it.
        is_default_colors = char.fg in ("default", None) and char.bg in ("default", None)

        if is_blank_space and is_default_colors:
            return Style(
                color=None if color == "default" else color,
                bgcolor=None if bgcolor == "default" else bgcolor
            )
        else:
            return Style(
                color=color if color != "default" else None,
                bgcolor=bgcolor if bgcolor != "default" else None,
                bold=char.bold, italic=char.italics, underline=char.underscore,
                strike=char.strikethrough, reverse=char.reverse,
            )
    except ColorParseError:
        return Style.null()


def normalize_event_key(event: events.Key) -> Tuple[str, bool, bool, bool, Optional[str], bool]:
    key = event.key
    parts = key.split("+")
    modifiers = set(parts[:-1])
    base_key = parts[-1]
    has_ctrl = "ctrl" in modifiers
    has_alt = "alt" in modifiers
    has_shift = "shift" in modifiers
    return base_key, has_ctrl, has_alt, has_shift, event.character, event.is_printable


def build_modifier_sequence(base_code: str, modifier_param: int) -> bytes:
    if "~" in base_code:
        n = base_code[:-1]
        final = base_code[-1]
        return f"\x1b[{n};{modifier_param}{final}".encode("ascii")
    else:
        return f"\x1b[1;{modifier_param}{base_code}".encode("ascii")


def get_key_bytes(event: events.Key) -> Optional[bytes]:
    base_key, has_ctrl, has_alt, has_shift, character, is_printable = normalize_event_key(event)

    # Priority 1: Direct full-key mapping (e.g., "ctrl+c", "shift+tab")
    if event.key in KEY_TRANSLATIONS:
        return KEY_TRANSLATIONS[event.key]

    # Priority 2: Algorithmic generation for special keys with modifiers
    if base_key in BASE_KEY_CODES and (has_ctrl or has_alt or has_shift):
        modifier_param = 1 + (1 if has_shift else 0) + (2 if has_alt else 0) + (4 if has_ctrl else 0)
        return build_modifier_sequence(BASE_KEY_CODES[base_key], modifier_param)

    # Priority 3: Alt prefix for other keys
    if has_alt:
        # Re-run logic for the key *without* alt to find its base sequence
        unmodified_key_event = events.Key(
            "+".join(p for p in event.key.split("+") if p != "alt"),
            character
        )
        unmodified_sequence = get_key_bytes(unmodified_key_event)
        if unmodified_sequence:
            return b"\x1b" + unmodified_sequence

    # Priority 4: Fallback for unmodified special keys or plain characters
    if base_key in KEY_TRANSLATIONS:
        return KEY_TRANSLATIONS[base_key]
    if is_printable and character:
        return character.encode("utf-8")

    return None


class Terminal(Widget, can_focus=True):
    scroll_offset = reactive(0, layout=True)

    def __init__(self, scrollback: int = 10000, **kwargs):
        super().__init__(markup=False, **kwargs)
        self._term_width = 80; self._term_height = 24
        self.history = deque(maxlen=scrollback)
        self.in_alternate_screen = False
        self._main_screen = CustomHistoryScreen(self._term_width, self._term_height, history=self.history, terminal_widget=self)
        self._alt_screen = Screen(self._term_width, self._term_height)
        self._main_stream = pyte.Stream(self._main_screen)
        self._alt_stream = pyte.Stream(self._alt_screen)
        self._screen = self._main_screen
        self.stream = self._main_stream
        self._line_cache: dict[int, Text] = {}
        self.master_fd: int | None = None; self.child_pid: int | None = None
        self.reader_thread: threading.Thread | None = None
        self.decode_buffer = b""
        self.cursor_visible = True
        self._cursor_timer = None

        # --- NEW: Self-managed mouse state flags ---
        self.normal_mouse_enabled = False
        self.button_event_mouse_enabled = False
        self.any_event_mouse_enabled = False
        self.sgr_mouse_enabled = False

    def on_mount(self) -> None:
        self._start_pty_process()
        self.reader_thread = threading.Thread(target=self._reader_thread_loop, daemon=True)
        self.reader_thread.start()
        self.call_later(self.focus)
        # --- Start the cursor blinking timer ---
        self._cursor_timer = self.set_interval(0.5, self._toggle_cursor)

    def on_unmount(self):
        if self.child_pid:
            try: os.kill(self.child_pid, 9)
            except ProcessLookupError: pass
        if self.master_fd:
            os.close(self.master_fd)
            self.master_fd = None

    def _toggle_cursor(self):
        self.cursor_visible = not self.cursor_visible
        self.refresh()

    def _start_pty_process(self):
        pid, master_fd = pty.fork()
        if pid == 0:
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            # shell = "/bin/bash"
            shell = os.environ.get("SHELL", "/bin/bash")
            os.execvpe(shell, [shell], env)
        else:
            self.child_pid, self.master_fd = pid, master_fd

    def _reader_thread_loop(self):
        while self.master_fd is not None:
            try:
                data = os.read(self.master_fd, 4096)
                if not data: break
                self.app.call_from_thread(self._process_pty_data, data)
            except (OSError, BlockingIOError): break

    def write_to_pty(self, data: bytes) -> None:
        """Safely write data directly to the PTY from the terminal widget."""
        print(f"[Terminal.write_to_pty] Writing response to PTY: {data!r}")
        if self.master_fd is not None:
            os.write(self.master_fd, data)

    def _process_pty_data(self, data: bytes):
        def _remove_control_strings(s: str) -> str:
            s = OSC_RE.sub('', s)
            s = DCS_RE.sub('', s)
            s = PM_RE.sub('', s)
            s = APC_RE.sub('', s)
            s = PRV_SGR_RE.sub('', s)
            return s
        for sequence, (mode_name, enabled) in MOUSE_PROTOCOLS.items():
            if sequence in data: setattr(self, f"{mode_name}_enabled", enabled)
        if ENTER_ALT_SCREEN in data and not self.in_alternate_screen:
            self.in_alternate_screen = True; self._screen = self._alt_screen; self.stream = self._alt_stream
            self._screen.reset(); self._line_cache.clear(); self.scroll_offset = 0
        if EXIT_ALT_SCREEN in data and self.in_alternate_screen:
            self.in_alternate_screen = False; self._screen = self._main_screen; self.stream = self._main_stream
            self._line_cache.clear(); self.scroll_offset = 0

        data = self.decode_buffer + data
        print(data)
        try:
            text = data.decode("utf-8")
            self.decode_buffer = b""
        except UnicodeDecodeError as e:
            text = data[:e.start].decode("utf-8")
            self.decode_buffer = data[e.start:]

        if text:
            # --- Sanitize the text stream before feeding it to pyte ---
            original_len = len(text)
            sanitized_text = _remove_control_strings(text)

            if len(sanitized_text) != original_len:
                print(f"Sanitized unsupported escape sequences. Removed {original_len - len(sanitized_text)} chars.")

            self.stream.feed(sanitized_text)

            dirty_lines = self._screen.dirty
            for y in dirty_lines:
                if y in self._screen.buffer:
                    self._line_cache[y] = self._render_pyte_line(self._screen.buffer[y])
            self._screen.dirty.clear()
            if self.scroll_offset == 0: self.refresh()
            else: self.dirty = True

    def _render_pyte_line(self, pyte_line: dict[int, Char]) -> Text:
        line_text = Text(no_wrap=True, end="")
        for x in range(self._screen.columns):
            char = pyte_line.get(x, self._screen.default_char)
            style = _pyte_to_rich_style(char)
            line_text.append(char.data, style)
        return line_text

    def render(self) -> Text:
        """A robust render method that always returns a full screen of lines."""
        lines: list[Text] = []
        history_len = len(self.history) if not self.in_alternate_screen else 0
        total_lines = history_len + self._screen.lines
        view_start = total_lines - self._screen.lines - self.scroll_offset

        for i in range(self._screen.lines):
            line_index = view_start + i
            line_to_render: Optional[Text] = None

            if 0 <= line_index < history_len:
                line_to_render = self._render_pyte_line(self.history[line_index])
            elif history_len <= line_index < total_lines:
                screen_y = line_index - history_len
                line_to_render = self._line_cache.get(screen_y)
                if line_to_render is None and screen_y in self._screen.buffer:
                    line_to_render = self._render_pyte_line(self._screen.buffer[screen_y])

            # --- THE FIX: Ensure a line is always appended ---
            lines.append(line_to_render if line_to_render is not None else Text(""))

        cursor = self._screen.cursor
        if self.has_focus and self.scroll_offset == 0 and not cursor.hidden and self.cursor_visible:
            y, x = cursor.y, cursor.x
            if 0 <= y < len(lines):
                line = lines[y].copy()
                if x < len(line.plain):
                    line.stylize("reverse", x, x + 1)
                else:
                    line.append(" ", "reverse")
                lines[y] = line

        return Text("\n").join(lines)

    def on_resize(self, event: events.Resize):
        self._term_width, self._term_height = event.size
        self._main_screen.resize(lines=self._term_height, columns=self._term_width)
        self._alt_screen.resize(lines=self._term_height, columns=self._term_width)
        self._line_cache.clear()
        if self.master_fd:
            winsize = struct.pack("HHHH", self._term_height, self._term_width, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        self.scroll_offset = 0
        self.refresh()

    def on_key(self, event: events.Key) -> None:
        """Handle key presses using the robust, xterm-compliant key handling system."""
        print(f"[on_key] entry. key={event.key!r}")

        # --- Priority 1: Check if this is a reserved GUI key ---
        if event.key in GUI_KEY_BINDINGS:
            print(f"[on_key] Key '{event.key}' is a GUI binding. Letting it bubble.")
            return

        # --- If not a GUI key, it belongs to the terminal ---
        if self.scroll_offset > 0: self.scroll_offset = 0
        if self.master_fd is None: return

        key_bytes = get_key_bytes(event)

        if key_bytes:
            # print(f"[on_key] Writing sequence: {key_bytes!r}")
            os.write(self.master_fd, key_bytes)
            event.stop()
        else:
            print(f"[on_key] No byte sequence determined for this key event.")
        # print("[on_key] exit")
        self.cursor_visible = True
        self._cursor_timer.reset()

    def _send_mouse_event(self, event: events.MouseEvent, button: int, state: str) -> bool:
        # print(f"[_send_mouse_event] entry. button={button}, state='{state}'")
        if not (self.sgr_mouse_enabled or self.any_event_mouse_enabled or self.button_event_mouse_enabled or self.normal_mouse_enabled):
            print("[_send_mouse_event] exit (no mouse reporting mode is enabled)")
            return False

        if self.sgr_mouse_enabled:
            x, y = event.x + 1, event.y + 1
            # --- THE FIX: Use event.meta for the alt key ---
            mod = (4 if event.shift else 0) + (8 if event.meta else 0) + (16 if event.ctrl else 0)
            final_button = button + mod
            sequence = f"\x1b[<{final_button};{x};{y}{state}".encode()

            # print(f"[_send_mouse_event] Sending SGR mouse event: {sequence!r}")
            if self.master_fd: os.write(self.master_fd, sequence)
            event.stop()
            return True

        print("[_send_mouse_event] exit (SGR mode not enabled, no fallback implemented)")
        return False

    def on_mouse_down(self, event: events.MouseDown) -> None:
        print(f"[on_mouse_down] entry. button={event.button}")
        if self._cursor_timer: self.cursor_visible = True; self._cursor_timer.reset()
        if not self._send_mouse_event(event, event.button - 1, "M"): self.focus()
        # print("[on_mouse_down] exit")

    def on_mouse_up(self, event: events.MouseUp) -> None:
        print(f"[on_mouse_up] entry. button={event.button}")
        self._send_mouse_event(event, event.button - 1, "m")
        # print("[on_mouse_up] exit")

    def on_mouse_move(self, event: events.MouseMove) -> None:
        is_drag = event.button != 0
        if self.any_event_mouse_enabled or (self.button_event_mouse_enabled and is_drag):
            button = (32 + event.button - 1) if is_drag else 35
            self._send_mouse_event(event, button, "M")

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        print("[on_mouse_scroll_up] entry")
        if not self._send_mouse_event(event, 64, "M"):
            if not self.in_alternate_screen: self.scroll_offset = min(len(self.history), self.scroll_offset + 1); self.refresh()
        # print("[on_mouse_scroll_up] exit")

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        print("[on_mouse_scroll_down] entry")
        if not self._send_mouse_event(event, 65, "M"):
            if not self.in_alternate_screen: self.scroll_offset = max(0, self.scroll_offset - 1); self.refresh()
        # print("[on_mouse_scroll_down] exit")


class Patty(Executable):
    """A simple terminal emulator."""
    APP_NAME = "Patty"
    APP_ID = "patty"
    APP_ICON_NAME = "terminal"
    APP_CATEGORY = "System Tools"
    MAIN_WIDGET = Terminal

    DEFAULT_CSS = """
    #app-content {
        border: none;
        width: 100%;
        height: 100%;
    }
    """
