from __future__ import annotations

from uuid import uuid4

import lib.display.glyphs as glyphs
from lib.core.widgets import UIButton
from textual import log, on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.css.scalar import Scalar, ScalarOffset, Unit
from textual.events import DescendantFocus, Key, MouseDown, MouseMove, MouseUp
from textual.geometry import Size
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, Static


class PriorityButton(UIButton):
    """ Handles on mousedown so it doesn't bubble up to the title bar"""
    def on_mouse_down(self, event: MouseDown) -> None:
        event.stop()


class TitleBar(Horizontal):
    """The title bar controls the window dragging state."""
    can_focus = True

    def __init__(self, window: Window):
        # Passes the parent window, so this component knows who to control.
        self._window = window
        super().__init__(id="title-bar")

    def compose(self) -> ComposeResult:
        """Composes the title and standard window buttons."""
        yield Static(
            f"{self._window.executable.app_icon}{self._window.executable.app_name}",
            id='window-title'
        )
        yield PriorityButton(glyphs.title_bar["minimize"], id='minimize-btn', compact=True)
        yield PriorityButton(glyphs.title_bar["maximize"], id='maximize-btn', compact=True)
        yield PriorityButton(glyphs.title_bar["exit"], id='exit-btn', compact=True)

    def on_mouse_down(self, event: MouseDown) -> None:
        """Initiates a window drag operation when the title bar is clicked."""
        if self._window.wm.mode == 'float':
            self._window.dragging = True
            self._window._mouse_offset_x = event.x
            self._window._mouse_offset_y = event.y
            self._window.capture_mouse()
            event.stop()


class Executable(Container):
    """
    A base class for creating windowed applications.

    This widget serves as the content area of a window, defining default
    behaviors and properties, and
    tells the chrome to become active, then passes focus to the main widget.
    """
    APP_NAME: str = "Untitled App"
    APP_ICON: str = " ● "
    MAIN_WIDGET: type[Widget] | None = None

    DEFAULT_CSS = """
    Executable {
        background: $surface;
        border: panel $surface;
        border-top: none;
        border-bottom: panel $surface;
        padding: 1 1 0 1;
        height: 2fr;
    }
    """
    window_offset = reactive((0, 0))

    def __init__(self, **kwargs):
        self.app_name = kwargs.pop("app_name", self.APP_NAME)
        self.app_icon = kwargs.pop("app_icon", self.APP_ICON)

        self._main_widget_kwargs = kwargs
        super().__init__(**kwargs)

        self._window: Window | None = None

    def on_mount(self) -> None:
        pass

    def focus_content(self) -> None:
        """A helper method to focus the main content widget"""
        if (content := self.query_one('#app-content', Widget)):
            content.focus()

    def compose(self) -> ComposeResult:
        """
        automatically creates an instance of the MAIN_WIDGET
        """
        if self.MAIN_WIDGET is not None:
            yield self.MAIN_WIDGET(id="app-content", **self._main_widget_kwargs)
        else:
            yield Label("This app has no content (MAIN_WIDGET is not defined).")


class Window(Container):
    """
    A non-focusable container for an application. It becomes 'active'
    when any of its children (title bar, buttons, executable) gain focus.
    """
    window_offset = reactive((0, 0))

    def __init__(self, executable: Executable, **kwargs):
        super().__init__(**kwargs)
        self.executable = executable
        self.executable._window = self  # to communicate with executable

        self._mouse_offset_x = 0
        self._mouse_offset_y = 0

        # Windows State Management
        self.dragging: bool = False
        self.user_offset: tuple[int, int] | None = None
        self.is_window_maximized: bool = False
        self.uuid = f"{uuid4().hex[:6]}"

        # Customization
        self.title_bar: None | bool | str = True

    def on_mount(self) -> None:
        """Get a reference to the WindowManager and pass focus to the executable."""
        self.wm = self.screen.query_one("#desktop", Container).wm
        self.window_offset = self.styles.offset  #fix for default 'restore' when offset not changed

    def compose(self) -> ComposeResult:
        """Composes the window with a TitleBar and the Executable content."""
        if self.title_bar:
            yield TitleBar(self)
        yield self.executable

    @on(DescendantFocus)
    def on_descendant_focus(self, event: DescendantFocus) -> None:
        """
        When any child widget is focused, tell the WindowManager to make this window active.
        We stop the event from bubbling further to prevent parent containers from reacting.
        """
        self.wm.set_active_window(self)
        event.stop()

    def on_key(self, event: Key) -> None:
        """Resize the widget from different edges with Ctrl+J/K/H/L."""
        def _recenter_widget(self):
            """Recalculate offset to keep widget centered in parent."""
            parent_size = self.parent.size if self.parent else self.app.size
            widget_size = self.size
            if not parent_size or not widget_size:
                return

            # Compute new offset in CELLS (not %)
            new_x = max((parent_size.width - widget_size.width) // 2, 0)
            new_y = max((parent_size.height - widget_size.height) // 2, 0)

            # Apply directly as cell units
            self.styles.offset = (new_x, new_y)
        def _to_cells(style_value) -> int:
            """Convert any Dimension/Scalar into an absolute cell count."""
            # Get size context
            size = self.parent.size if self.parent else self.size
            viewport = self.app.size if self.app else Size(80, 24)

            try:
                return int(round(style_value.resolve(size, viewport)))
            except Exception:
                return int(style_value.value or 0)

        # --- Extract current style values in cells ---
        h = _to_cells(self.styles.height)
        w = _to_cells(self.styles.width)
        # t = self.styles.offset
        # print("---------------------\n",t)
        # l = to_cells(self.styles.margin.left)

        # --- Handle key events ---
        match event.key:
            case "ctrl+j":  # grow upward
                # self.styles.margin.top = max(t - 1, 0)
                self.styles.height = h + 1

            case "ctrl+k":  # grow downward
                self.styles.height = h + 1

            case "ctrl+h":  # grow leftward
                # self.styles.margin.left = max(l - 1, 0)
                self.styles.width = w + 1

            case "ctrl+l":  # grow rightward
                self.styles.width = w + 1

            case "ctrl+shift+j":  # shrink from top
                # self.styles.margin.top = t + 1
                self.styles.height = max(h - 1, 1)

            case "ctrl+shift+k":  # shrink from bottom
                self.styles.height = max(h - 1, 1)

            case "ctrl+shift+h":  # shrink from left
                # self.styles.margin.left = l + 1
                self.styles.width = max(w - 1, 1)

            case "ctrl+shift+l":  # shrink from right
                self.styles.width = max(w - 1, 1)
        _recenter_widget(self)
        self.refresh(layout=True)


    def on_mouse_up(self, event: MouseUp) -> None:
        """Releases the drag lock when the mouse button is released."""
        if self.dragging:
            self.dragging = False
            self.release_mouse()
            event.stop()

    def on_mouse_move(self, event: MouseMove) -> None:
        """Moves the window and record the new user offset"""
        if self.dragging:
            new_offset = (event.screen_x - self._mouse_offset_x, event.screen_y - self._mouse_offset_y)
            # Explicitly storing the user's action
            self.styles.offset = self.window_offset
            self.user_offset = new_offset
            self.window_offset = new_offset
            self.styles.offset = new_offset
            event.stop()

    def watch_window_offset(self, old_offset: tuple[int, int], new_offset: tuple[int, int]) -> None:
        """Syncs the window's offset with its underlying executable."""
        # log(f"Window moved to {new_offset}") # debug
        if hasattr(self.executable, 'window_offset'):
            self.executable.window_offset = new_offset

    @on(Button.Pressed, "#exit-btn")
    def close_window(self, event: Button.Pressed) -> None:
        log(f"Closing window for {self.executable.app_name}")
        self.app.call_next(self.wm.close_window, self)
        event.stop()

    @on(Button.Pressed, "#minimize-btn")
    def minimize_window(self, event: Button.Pressed) -> None:
        log(f"Minimizing window for {self.executable.app_name}")
        self.display = False
        event.stop()

    @on(Button.Pressed, "#maximize-btn")
    def toggle_maximize_window(self, event: Button.Pressed) -> None:
        """Updates internal state and tells the WindowManager to handle the visuals."""
        self.is_window_maximized = not self.is_window_maximized
        self.wm.handle_window_maximized(self)
        self.query_one('#maximize-btn').label = glyphs.title_bar["restore"] if self.is_window_maximized else glyphs.title_bar["maximize"]
        event.stop()
