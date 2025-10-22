import fcntl
import os
import pty
import struct
import termios
import threading

import pyte
from pyte.screens import Char
from rich.color import ColorParseError
from rich.style import Style
from rich.text import Text
from textual import events, log
from textual.app import App, ComposeResult
from textual.color import Color
from textual.theme import Theme  # Import the Theme object
from textual.widget import Widget

# This new mapping connects pyte's color names to semantic Textual CSS variables.
PYTE_TO_CSS_VAR = {
    # Normal Colors
    "black": "surface",
    "red": "error",
    "green": "success",
    "brown": "warning",  # pyte uses "brown" for yellow
    "blue": "primary",
    "magenta": "accent",
    "cyan": "secondary",
    "white": "foreground",
    # Bright Colors -> map to lighter shades of the base colors
    "brightblack": "foreground-muted",
    "brightred": "error-lighten-2",
    "brightgreen": "success-lighten-2",
    "brightyellow": "warning-lighten-2",
    "brightblue": "primary-lighten-2",
    "brightmagenta": "accent-lighten-2",
    "brightcyan": "secondary-lighten-2",
    "brightwhite": "foreground-darken-1", # A slightly off-white for contrast
}

KEY_TRANSLATIONS = {
    "up": b"\x1b[A", "down": b"\x1b[B", "right": b"\x1b[C", "left": b"\x1b[D",
    "home": b"\x1b[H", "end": b"\x1b[F", "pageup": b"\x1b[5~", "pagedown": b"\x1b[6~",
    "delete": b"\x1b[3~", "insert": b"\x1b[2~", "ctrl+c": b"\x03", "ctrl+d": b"\x04",
}

class Terminal(Widget, can_focus=True):
    """A theme-aware, performant terminal emulator that uses Textual CSS variables."""

    DEFAULT_CSS = """
    Terminal {
        background: $background;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # The widget no longer takes a 'theme' dictionary.
        self._term_width = 80
        self._term_height = 24
        self.pyte_screen = pyte.Screen(self._term_width, self._term_height)
        self.pyte_stream = pyte.ByteStream(self.pyte_screen)
        
        self.master_fd: int | None = None
        self.child_pid: int | None = None
        self.reader_thread: threading.Thread | None = None
        
        self._line_cache: dict[int, Text] = {}
        self._last_cursor_pos = (-1, -1)
        
        # This cache will store the resolved hex codes from the current theme's
        # CSS variables. It's populated at the start of render().
        self._color_cache: dict[str, str] = {}

    def _populate_color_cache(self) -> None:
        """Resolves all CSS variables and populates the color cache."""
        for pyte_color, css_var in PYTE_TO_CSS_VAR.items():
            try:
                # get_css_variable returns a Color object. We get its hex code.
                self._color_cache[pyte_color] = self.get_css_variable(css_var).hex
            except ColorParseError:
                # Fallback if a variable is not defined for some reason
                log.warning(f"Could not resolve CSS variable ${css_var}")
                self._color_cache[pyte_color] = "#ff00ff" # Default to magenta for errors
        
        # Add the base foreground and background
        self._color_cache["foreground"] = self.get_css_variable("foreground").hex
        self._color_cache["background"] = self.get_css_variable("background").hex

    def _pyte_to_rich_style(self, char: Char) -> Style:
        """Converts a pyte.Char to a rich.style.Style using the cached theme colors."""

        def get_color_from_cache(pyte_color: str, is_bg: bool = False) -> str:
            """Takes a color string from pyte and gets its hex value from the cache."""
            if pyte_color == "default":
                return self._color_cache["background"] if is_bg else self._color_cache["foreground"]
            
            # Use the cached hex code for the pyte color name
            cached_color = self._color_cache.get(pyte_color)
            if cached_color:
                return cached_color

            # Handle direct hex/rgb specifications from advanced terminals
            if ";" in pyte_color: return f"rgb({','.join(pyte_color.split(';'))})"
            if len(pyte_color) == 6 and all(c in '0123456789abcdef' for c in pyte_color.lower()):
                return f"#{pyte_color}"
            if pyte_color.isdigit(): return pyte_color # Passthrough for 256 colors

            # Final fallback
            return self._color_cache["background"] if is_bg else self._color_cache["foreground"]

        try:
            color = get_color_from_cache(char.fg)
            bgcolor = get_color_from_cache(char.bg, is_bg=True)
            return Style(
                color=color, bgcolor=bgcolor, bold=char.bold, italic=char.italics,
                underline=char.underscore, strike=char.strikethrough, reverse=char.reverse,
            )
        except (ColorParseError, KeyError):
            return Style.null()

    def render(self) -> Text:
        # --- KEY IMPROVEMENT ---
        # Re-populate the color cache every time we render. This ensures that if
        # the theme changes, the terminal will instantly reflect it on the next frame.
        self._populate_color_cache()
        # ---

        screen_text = Text(no_wrap=True)
        cursor = self.pyte_screen.cursor
        is_cursor_visible = not cursor.hidden and self.has_focus
        dirty_lines = self.pyte_screen.dirty
        
        # The rest of the render method is largely the same, but now uses the
        # updated _pyte_to_rich_style which relies on the cache.
        if self._last_cursor_pos != (cursor.y, cursor.x):
            dirty_lines.add(self._last_cursor_pos[0])
            dirty_lines.add(cursor.y)
        self._last_cursor_pos = (cursor.y, cursor.x)

        for y in dirty_lines:
            line = self.pyte_screen.buffer.get(y, {})
            line_text = Text(no_wrap=True)
            last_style, current_run = None, ""
            for x in range(self.pyte_screen.columns):
                char = line.get(x, self.pyte_screen.default_char)
                style = self._pyte_to_rich_style(char)
                if style != last_style:
                    if current_run: line_text.append(current_run, last_style)
                    current_run, last_style = char.data, style
                else:
                    current_run += char.data
            if current_run: line_text.append(current_run, last_style)
            self._line_cache[y] = line_text
        self.pyte_screen.dirty.clear()

        all_lines = [self._line_cache.get(y, Text(" " * self._term_width)) for y in range(self.pyte_screen.lines)]
        if is_cursor_visible:
            y, x = cursor.y, cursor.x
            if 0 <= y < len(all_lines):
                line = all_lines[y]
                if x < len(line.plain):
                    line.stylize_before("reverse", start=x, end=x + 1)
                else:
                    line.append(" ", style="reverse")
        return Text("\n").join(all_lines)
    
    # ... on_mount, on_unmount, on_key, on_resize, and PTY methods remain the same ...
    def on_mount(self) -> None:
        self.on_resize(events.Resize(self.size, self.size)) # Initial resize
        self._start_pty_process()

    def on_unmount(self) -> None:
        if self.child_pid:
            try: os.kill(self.child_pid, 9)
            except ProcessLookupError: pass
        if self.master_fd:
            os.close(self.master_fd)

    def on_key(self, event: events.Key) -> None:
        if self.master_fd is None: return
        if event.key in KEY_TRANSLATIONS:
            os.write(self.master_fd, KEY_TRANSLATIONS[event.key])
        elif event.character:
            os.write(self.master_fd, event.character.encode())

    def on_resize(self, event: events.Resize) -> None:
        self._line_cache.clear()
        self._term_width, self._term_height = event.size.width, event.size.height
        self.pyte_screen.resize(lines=self._term_height, columns=self._term_width)
        if self.master_fd:
            size_data = struct.pack("HHHH", self._term_height, self._term_width, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, size_data)

    def _start_pty_process(self) -> None:
        pid, master_fd = pty.fork()
        if pid == 0:
            shell = os.environ.get("SHELL", "/bin/bash")
            os.execv(shell, [shell])
        else:
            self.child_pid, self.master_fd = pid, master_fd
            self.reader_thread = threading.Thread(target=self._read_from_pty, daemon=True)
            self.reader_thread.start()

    def _read_from_pty(self) -> None:
        while self.master_fd is not None:
            try:
                data = os.read(self.master_fd, 1024)
                if not data: break
                self.app.call_from_thread(self._write_to_pyte, data)
            except OSError: break

    def _write_to_pyte(self, data: bytes) -> None:
        self.pyte_stream.feed(data)
        self.refresh()

# --- HOW TO USE THE IMPROVED WIDGET ---
# Define a proper Textual Theme object
patty_theme = Theme(
    name="patty_nord",
    primary="#81A1C1",
    secondary="#88C0D0",
    accent="#B48EAD",
    foreground="#D8DEE9",
    background="#2E3440",
    surface="#3B4252",
    success="#A3BE8C",
    warning="#EBCB8B",
    error="#BF616A",
    dark=True,
)


# Faking the Executable and glyphs for a runnable example
class Executable: pass
class glyphs:
    class icons:
        def get(self, *args, **kwargs): return "T"

class Patty(App, Executable):
    APP_NAME = "patty"
    
    # We don't need to pass anything to the Terminal anymore
    def compose(self) -> ComposeResult:
        yield Terminal()

    def on_mount(self) -> None:
        # Correctly register the theme with the app
        self.register_theme(patty_theme)
        # Set it as the current theme
        self.theme = "patty_nord"

if __name__ == "__main__":
    app = Patty()
    app.run()
