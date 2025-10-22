"""
attempt at implementing & fixing the scrollback buffer
outsourced the debug to llm: it didn't work
idk how to continue with this, but it could be useful in the future
"""

# from lib.display.console import log
import fcntl
import os
import pty
import re
import shutil
import struct
import termios
import threading
from collections import deque

import lib.display.glyphs as glyphs
import pyte
from lib.display.console import log
from lib.display.window import Executable
from pyte.screens import Char
from rich.style import Style
from rich.text import Text
from textual import events
from textual.geometry import Size
from textual.widget import Widget

RE_IS_CLEAR_SCREEN = re.compile(r"\x1b\[[23]?J")

KEY_TRANSLATIONS = {
    "up": b"\x1b[A", "down": b"\x1b[B", "right": b"\x1b[C", "left": b"\x1b[D",
    "home": b"\x1b[H", "end": b"\x1b[F", "delete": b"\x1b[3~", "insert": b"\x1b[2~",
    "pageup": b"\x1b[5~", "pagedown": b"\x1b[6~",
    "ctrl+c": b"\x03", "ctrl+d": b"\x04", "ctrl+l": b"\x0c",
}


class HistoryScreen(pyte.Screen):
    """
    A pyte screen that correctly handles shrinking by treating the entire
    old viewport as new history.
    """
    def __init__(self, columns, lines, history, renderer):
        super().__init__(columns, lines); self.history = history; self._render_pyte_line = renderer

    # This resize logic is now correct and robust.


    def resize(self, lines=None, columns=None):
        """
        Correctly handles resizing by manually scrolling the buffer up N times
        using the index() method, which correctly populates the history.
        """
        old_lines = self.lines
        new_lines = lines if lines is not None else old_lines

        # Ensure capturing is enabled so our index() override works as intended.
        self._capturing_enabled = True

        if new_lines < old_lines:
            lines_to_scroll = old_lines - new_lines
            # Triggering index() N times is the correct, idiomatic way to scroll
            # the buffer up N lines. Our overridden index() will handle
            # capturing each scrolled line to the history buffer.
            for _ in range(lines_to_scroll):
                self.index()

        # After manually adjusting the buffer, disable capturing to prevent
        # any unexpected history additions from the super().resize() call.
        self._capturing_enabled = False

        # Now, perform the actual destructive resize from the parent.
        super().resize(lines, columns)

        # Re-enable capturing for normal operation.
        self._capturing_enabled = True

    def index(self):
        """
        Overrides the default pyte scroll-up behavior to capture the
        scrolled-off line into our history buffer.
        """
        if self._capturing_enabled:
            line_to_capture = self.buffer.get(0, {})
            if any(char.data != " " for char in line_to_capture.values()):
                rendered = self._render_pyte_line(line_to_capture)
                if not self.history or self.history[-1] != rendered:
                    self.history.append(rendered)

        # Call the parent method to perform the actual buffer scroll.
        super().index()


class Terminal(Widget, can_focus=True):
    SCROLLBACK_LIMIT = 2000

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._term_width, self._term_height = 80, 24
        self._scrollback = deque(maxlen=self.SCROLLBACK_LIMIT)
        self.pyte_screen = HistoryScreen(
            self._term_width, self._term_height, self._scrollback, self._render_pyte_line
        )
        self.pyte_stream = pyte.Stream(self.pyte_screen)
        self.master_fd = None
        self.child_pid = None
        self.reader_thread = None
        self._scroll_offset = 0
        self._shell_ready = False

    def _run_diagnostic_script(self):
        import time

        def resize_terminal(new_height):
            new_size = Size(self.size.width, new_height)
            self._update_size_attributes(new_size)
            self.app.call_from_thread(lambda: self.on_resize(events.Resize(new_size, new_size)))
            # self.on_resize(events.Resize(new_size))
            # log(f"resiz... done resizing to height={new_height}")

        def log_visible(step):
            rendered = self.render()
            if rendered.plain.strip():
                log(f"\n==== [{step}] ====\n{rendered.plain}\n{'=' * 40}")
            else:
                log(f"[{step}] Rendered output was empty.")

        time.sleep(0.3)
        log("diagnostic step: resize to 7")
        resize_terminal(7)
        log("diagnostic step: after resize to 7, sleeping 0.5s")
        time.sleep(0.5)
        log_visible("Step 1: Height 7")

        log("diagnostic step: writing seq 1 100; echo done")
        os.write(self.master_fd, b"seq 1 100; echo done\n")
        log("diagnostic step: sleeping 1.0s")
        time.sleep(1.0)
        log_visible("Step 2: After seq 1 100")

        log("diagnostic step: resize to 10")
        resize_terminal(10)
        log("diagnostic step: sleeping 0.3s")
        time.sleep(0.3)
        log_visible("Step 3: Resize to 10")

        log("diagnostic step: resize to 3")
        resize_terminal(3)
        log("diagnostic step: sleeping 0.3s")
        time.sleep(0.3)
        log_visible("Step 4: Resize to 3")

        log("diagnostic step: resize to 10 again")
        resize_terminal(10)
        log("diagnostic step: sleeping 0.3s")
        time.sleep(0.3)
        log_visible("Step 5: Resize to 10 again")

    def on_mount(self):
        self._update_size_attributes(self.size)
        self._start_pty_process()

    def on_unmount(self):
        if self.child_pid:
            try: os.kill(self.child_pid, 9)
            except ProcessLookupError: pass
        if self.master_fd:
            os.close(self.master_fd)
        self.master_fd = None
    def _update_size_attributes(self, size: Size):
        """A simple helper to update internal size state."""
        self._term_height = max(1, size.height)
        self._term_width = max(1, size.width)
        self._scroll_offset = 0

    def on_resize(self, event: events.Resize):
        """
        Handles resizing by updating attributes and notifying pyte and the PTY.
        This version removes the destructive reset() call and relies on the
        standard shell redraw mechanism.
        """
        self._update_size_attributes(event.size)

        # Our HistoryScreen wrapper will correctly handle history on shrink.
        # Pyte's resize will handle buffer reflowing.
        self.pyte_screen.resize(lines=self._term_height, columns=self._term_width)

        # Notify the PTY of the new size. This triggers SIGWINCH in the shell,
        # which is responsible for sending the correct redraw commands.
        if self.master_fd:
            winsize = struct.pack("HHHH", self._term_height, self._term_width, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

        self.refresh()

    def on_key(self, event: events.Key):
        if self.master_fd is None: return

        if event.key in ("pageup", "pagedown"):
            max_scroll = max(0, len(self._scrollback))
            scroll_amount = 1
            if event.key == "pageup":
                self._scroll_offset = min(self._scroll_offset + scroll_amount, max_scroll)
            else:
                self._scroll_offset = max(self._scroll_offset - scroll_amount, 0)
            self.refresh()
            return

        self._scroll_offset = 0
        if event.key in KEY_TRANSLATIONS:
            os.write(self.master_fd, KEY_TRANSLATIONS[event.key])
        elif event.character:
            os.write(self.master_fd, event.character.encode())

    def on_mouse_scroll_up(self, event: events.MouseScrollUp):
        max_scroll = max(0, len(self._scrollback))
        self._scroll_offset = min(self._scroll_offset + 3, max_scroll)
        self.refresh()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown):
        self._scroll_offset = max(self._scroll_offset - 3, 0)
        self.refresh()

    def render(self) -> Text:
        live_lines = [
            self._render_pyte_line(self.pyte_screen.buffer.get(y, {}))
            for y in range(self.pyte_screen.lines)
        ]
        history_and_screen = list(self._scrollback) + live_lines

        total_lines = len(history_and_screen)
        view_end = total_lines - self._scroll_offset
        view_start = max(0, view_end - self._term_height)
        display_lines = history_and_screen[view_start:view_end]

        if self._scroll_offset == 0 and self.has_focus and not self.pyte_screen.cursor.hidden:
            cursor = self.pyte_screen.cursor
            cursor_display_y = len(display_lines) - (self.pyte_screen.lines - cursor.y)

            if 0 <= cursor_display_y < len(display_lines):
                line = display_lines[cursor_display_y]
                if cursor.x < len(line.plain):
                    line.stylize("reverse", start=cursor.x, end=cursor.x + 1)
                else:
                    line.append(" " * (cursor.x - len(line.plain)))
                    line.append(" ", style="reverse")

        while len(display_lines) < self._term_height:
            display_lines.append(Text(""))

        return Text("\n").join(display_lines)

    def _render_pyte_line(self, line: dict[int, Char]) -> Text:
        line_text = Text(no_wrap=True, end="")
        last_style = None
        current_run = ""
        max_x = -1
        if line: max_x = max(line.keys())
        for x in range(min(self._term_width, max_x + 1)):
            char = line.get(x, self.pyte_screen.default_char)
            style = self._pyte_to_rich_style(char)
            if style != last_style and current_run:
                line_text.append(current_run, last_style)
                current_run = ""
            current_run += char.data
            last_style = style
        if current_run: line_text.append(current_run, last_style)
        return line_text

    def _write_data(self, data: bytes):
        text = data.decode("utf-8", "replace")
        # log(f"[PTY OUTPUT] {repr(text[:100])}")
        if "λ" in text and "~/Documents" in text and not self._shell_ready:
            self._shell_ready = True
            log("[diagnostic] Shell prompt detected")
            threading.Thread(target=self._run_diagnostic_script, daemon=True).start()

        if RE_IS_CLEAR_SCREEN.search(text):
            self._scrollback.clear()
        self.pyte_stream.feed(text)
        self.refresh()

    def _start_pty_process(self):
        pid, master_fd = pty.fork()
        if pid == 0:
            winsize = struct.pack("HHHH", self._term_height, self._term_width, 0, 0)
            fcntl.ioctl(pty.STDIN_FILENO, termios.TIOCSWINSZ, winsize)
            os.execv("/bin/bash", ["/bin/bash", "-i"])
        else:
            self.child_pid = pid
            self.master_fd = master_fd
            self.reader_thread = threading.Thread(target=self._read_from_pty, daemon=True)
            self.reader_thread.start()

    def _read_from_pty(self):
        while True:
            try:
                # This read will block until data is available or the fd is closed.
                data = os.read(self.master_fd, 4096)
                if not data: # An empty read indicates the PTY has closed.
                    break
                # Schedule the data processing on the main Textual event loop.
                self.app.call_from_thread(self._write_data, data)
            except (OSError, AttributeError):
                # OSError will be raised if the fd is closed while blocking.
                # AttributeError can happen if the app is torn down.
                break

        # Schedule the widget for removal when the process ends.
        if self.app and self.is_running:
            self.app.call_from_thread(self.remove)

    def _pyte_to_rich_style(self, char: Char) -> Style:
        COLOR_MAP = { "brown": "yellow", "brightbrown": "yellow", "brightblack": "#555555", "brightred": "#ff5555", "brightgreen": "#55ff55", "brightyellow": "#ffff55", "brightblue": "#5555ff", "brightmagenta": "#ff55ff", "brightcyan": "#55ffff", "brightwhite": "#ffffff", "black": "#000000", "red": "#aa0000", "green": "#00aa00", "yellow": "#aa5500", "blue": "#0000aa", "magenta": "#aa00aa", "cyan": "#00aaaa", "white": "#aaaaaa" }
        def fix_color(color: str, default: str) -> str:
            if not color or color == "default": return default
            if color in COLOR_MAP: return COLOR_MAP[color]
            if re.fullmatch(r"[0-9a-fA-F]{6}", color): return f"#{color}"
            return "red"
        fg = fix_color(char.fg, "white")
        bg = fix_color(char.bg, "black")
        style = Style(color=fg, bgcolor=bg)
        if char.bold: style += Style(bold=True)
        if char.reverse: style += Style(reverse=True)
        if char.italics: style += Style(italic=True)
        if char.underscore: style += Style(underline=True)
        return style


class Patty(Executable):
    """The Executable application wrapper for the Terminal widget."""
    APP_NAME = "Patty"

    @property
    def APP_ICON(self):
        return glyphs.icons.get("terminal", "?")

    MAIN_WIDGET = Terminal


"""
    Top-level Overview:
    - Backend: uses `pty` to spawn and interact with a real shell
    - Async: uses threads to read shell output
    - Screen emulation: `pyte` parses escape codes into a virtual screen
    - Rendering: converts pyte screen into `Textual` widgets

    Debug Summary apparently



High-Level Problem

Implementing a scrollback buffer for a PTY-backed terminal is fundamentally a three-way state synchronization problem between:

    The Shell Process (bash): The ground truth of the screen's content and cursor position.

    The Emulator (pyte): A simulation of the screen that can become desynchronized.

    The Widget (_scrollback deque): Our own history buffer.

Resizing the widget is a destructive event that violently breaks this synchronization, leading to a cascade of visual bugs.
The Core Technical Challenge: pyte.Screen.resize()

The root of all issues is that pyte's resize method is insufficient and destructive:

    When shrinking, it truncates its internal buffer, permanently deleting lines from the bottom. This is not a simple scroll.

    The internal text reflowing logic is complex and does not reliably trigger the index() (scroll) method in a way we can use for history capture.

This destructive behavior means we cannot simply call pyte.resize() and expect things to work. We must manually manage the state transition.
The Chain of Flawed Solutions (The Traps to Avoid)

Our debugging journey fell into three major traps, each fixing one bug while creating another:

    Trap 1: The "Simple History Capture" (index() override)

        Goal: Capture lines when pyte scrolls them off screen.

        Failure: pyte.resize() also triggers index(), causing a race condition where we'd capture a line right before the shell redrew it, resulting in line duplication.

    Trap 2: The "Nuke" Approach (pyte_screen.reset())

        Goal: Fix visual artifacts by wiping the pyte screen on resize, forcing the shell to redraw on a clean slate.

        Failure: The shell's redraw after a resize signal (SIGWINCH) is often minimal. It redraws the prompt but assumes the output above it is still there. Since we wiped the screen, this resulted in massive content loss, leaving only the prompt on an empty screen.

    Trap 3: The "Surgical Rescue" Approach (modifying HistoryScreen.resize)

        Goal: Before pyte destructively shrinks its buffer, try to "rescue" the lines that will be deleted and move them to our scrollback.

        Failure: This was the deepest part of the rabbit hole. Our attempts were flawed because:

            Incorrect Heuristics: We tried to guess which lines to save (e.g., range(new, old), y == cursor.y). These heuristics were fragile and inevitably failed with multi-line prompts or complex screen states.

            Fundamental Flaw: We incorrectly captured the live prompt and moved it into the history buffer. This is the single biggest cause of the visual corruption seen in the final diagnostic logs (invisible prompt, stale prompts appearing on expand).

The Path Forward: The Correct (but Complex) Architecture

A truly robust scrollback implementation would require emulating a real terminal's behavior precisely:

    On Shrink: Before resizing, take a snapshot of the entire current pyte screen and append all of its lines to the _scrollback deque. This treats the entire old viewport as a single block of new history.

    Clean Slate: After saving the history, call pyte_screen.reset() to completely clear the (now stale) live view.

    Notify: Call fcntl.ioctl() to send the SIGWINCH signal. The shell will then redraw its prompt onto the pristine, empty live screen.

This "snapshot-and-reset" approach avoids all fragile heuristics. However, it requires careful implementation to feel seamless. The simpler, no-scrollback version was chosen because it prioritizes correctness and stability over a feature that proved to be a source of deep, architectural bugs.
"""
