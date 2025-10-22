from uuid import uuid4

from textual import log, on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.dom import DOMNode
from textual.events import (Blur, DescendantBlur, DescendantFocus, Key,
                            MouseDown, MouseMove, MouseUp)
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Static


class Handle(Static):
    """
    The draggable title bar of a window.

    This component captures mouse events to move its parent `Window` container.
    """
    can_focus = True

    def __init__(self, label: str, id: str | None = None, **kwargs):
        super().__init__(id=id, **kwargs)
        self.label = label

    def on_mount(self):
        self.window = self.parent.parent

    def compose(self) -> ComposeResult:
        yield Static(self.label, id=self.id)

    async def on_mouse_down(self, event: MouseDown) -> None:
        """Initiates a window drag operation."""
        # self.parent can be none
        if self.window and self.window.wm.mode == 'float':
            self.window.dragging = True
            self.window._mouse_offset_x = event.x
            self.window._mouse_offset_y = event.y
            self.window.capture_mouse()
            event.stop()


class Executable(Container):
    """
    A base class for creating windowed applications.

    This widget serves as the content area of a window, defining default
    behaviors and properties, and
    tells the chrome to become active, then pass focus down the main content.

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
        padding: 0 1 0 1;
        height: 2fr;    }
    """
    window_offset = reactive((0, 0))

    def __init__(self, **kwargs):
        self.app_name = kwargs.pop("app_name", self.APP_NAME)
        self.app_icon = kwargs.pop("app_icon", self.APP_ICON)
        super().__init__(**kwargs)
        self._window: Window | None = None

    def on_mount(self) -> None:
        pass

    def focus_content(self) -> None:
        """A helper method to focus the main content widget"""
        if (content := self.query_one('#app-content', Widget)):
            content.focus()

    def on_mouse_down(self, event: MouseDown) -> None:
        if self._window is not None:
            self._window.wm.set_active_window(self._window)

    def compose(self) -> ComposeResult:
        """
        automatically creates an instance of the MAIN_WIDGET
        """
        if self.MAIN_WIDGET is not None:
            # The main content widget gets a specific ID for easy querying and styling.
            yield self.MAIN_WIDGET(id="app-content")
        else:
            from textual.widgets import Label
            yield Label("This app has no content (MAIN_WIDGET is not defined).")


class Window(Container):
    """
    A container for an application, providing standard window features.

    This includes a title bar, control buttons (minimize, maximize, close),
    and drag-and-drop functionality. It wraps an `Executable` widget.
    * Only: owns its personal states, report events up to wm, provides chrome
    """
    window_offset = reactive((0, 0))

    def __init__(self, executable: Executable, **kwargs):
        super().__init__(**kwargs)
        self.executable = executable
        self.dragging: bool = False
        self._mouse_offset_x = 0
        self._mouse_offset_y = 0
        self.executable._window = self  # to communicate with executable

        # Windows State Management
        self.user_offset: tuple[int, int] | None = None
        self.is_window_maximized: bool = False
        self.uuid = f"{uuid4().hex[:6]}"

    def on_mount(self) -> None:
        self.wm = self.screen.query_one("#desktop", Container).wm


    def compose(self) -> ComposeResult:
        with Horizontal(id="title-bar"):
            yield Handle(f"{self.executable.app_icon}{self.executable.app_name}", id='window-title')
            yield Button("-", id='minimize-btn', compact=True)
            yield Button('൦', id='maximize-btn', compact=True)
            yield Button("✕", id='exit-btn', compact=True)
        yield self.executable

    def on_key(self, event: Key) -> None:
        # Notify the WM before removing, so it can manage focus transfer.
        if event.key == "alt+q":
            self.wm.handle_window_close(self)
        else:
            self.executable.focus()

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
        log(f"Window moved to {new_offset}")
        if hasattr(self.executable, 'window_offset'):
            self.executable.window_offset = new_offset

    @on(Button.Pressed, "#exit-btn")
    def close_window(self, event: Button.Pressed) -> None:
        log(f"Closing window for {self.executable.app_name}")
        self.wm.handle_window_close(self)
        self.remove()
        event.stop()

    @on(Button.Pressed, "#minimize-btn")
    def minimize_window(self, event: Button.Pressed) -> None:
        log(f"Minimizing window for {self.executable.app_name}")
        self.display = False
        event.stop()

    @on(Button.Pressed, "#maximize-btn")
    def toggle_maximize_window(self, event: Button.Pressed) -> None:
        """Toggles the window between a maximized and restored state."""
        self.focus()

        self.wm.handle_window_maximized(self)
        self.is_window_maximized = not self.is_window_maximized
        if self.is_window_maximized:
            self.query_one('#maximize-btn').label = '൦'
        else:
            self.query_one('#maximize-btn').label = '⛶'
        event.stop()
