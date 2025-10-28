from __future__ import annotations

from uuid import uuid4

import lib.display.glyphs as glyphs
from lib.core.widgets import UIButton
from textual import log, on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.events import (DescendantFocus, Key, Leave, MouseDown, MouseMove,
                            MouseUp)
from textual.geometry import Offset, Region, Size
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, Static


class PriorityButton(UIButton):
    """A button that stops MouseDown events from bubbling to its parent."""
    def on_mouse_down(self, event: MouseDown) -> None:
        event.stop()


class TitleBar(Horizontal):
    """The title bar for a Window, handles drag initiation and window controls."""
    can_focus = True

    def __init__(self, window: Window):
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
        if self._window.wm.mode == 'float':  # to refactor: move wm logic to wm
            self._window.start_drag(event)
            # event.stop()


class Executable(Container):
    """
    A base class for creating windowed applications. This widget serves as the
    content area of a window.
    """
    APP_ID: str = 'base_app'
    APP_NAME: str = "Untitled App"
    APP_ICON: str = " ~ "
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

    def focus_content(self) -> bool:
        """A helper method to focus the main content of the main widget"""
        try:
            content_container = self.query_one('#app-content', Widget)
            all_descendants = content_container.query("*")
            focusable_descendants = [
                widget
                for widget in all_descendants
                if widget.can_focus and not widget.disabled
            ]
            if focusable_descendants:
                target_to_focus = focusable_descendants[-1]
                log(f"Smart focus found target: {target_to_focus}")
                target_to_focus.focus()
                return True
            else:
                log(f"Smart focus found no descendants in {content_container}")
                return False

        except Exception as e:
            # if #app-content doesn't exist or no focus target can be found
            log(f"Error during smart focus: {e}")
            return False

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
    A draggable and resizable container for an Executable application. It becomes
    'active' when any of its children gain focus.
    """
    window_offset = reactive((0, 0))
    can_focus = True

    def __init__(self, executable: Executable, **kwargs):
        super().__init__(**kwargs)
        self.executable = executable
        self.executable._window = self

        # Windows State Management
        self.is_window_dragging: bool = False
        self.is_window_resizing: bool = False
        self.is_window_maximized: bool = False
        self.user_offset: tuple[int, int] | None = None
        self.window_size: tuple[int, int] | None = None  # window size state snapshot
        self.uuid = f"{uuid4().hex[:6]}"

        # Drag and Resize Internals
        self._drag_offset: tuple[int, int] = (0, 0)
        self._resize_edge: set[str] | None = set()
        self._resize_start: tuple[int, int] | None = (0, 0)
        self._resize_origin: tuple[int, int, int, int] | None = (0, 0, 0, 0)
        self._last_hover_state: dict[str, bool] | None = None

        # Customization
        self.title_bar: None | bool | str = True
        self.EDGE_MARGIN: int = 1
        self.MIN_WIDTH: int = 12
        self.MIN_HEIGHT: int = 4
        self.init_width: int = 80
        self.init_height: int = 20

        # Support
        self.multiple_instance: bool = True

    # ┌───────────────────────────────────────────────────────────────────────┐
    # │ Lifecycle & Compose Methods                                           │
    # └───────────────────────────────────────────────────────────────────────┘

    def on_mount(self) -> None:
        """Get a reference to the WindowManager and set initial offset."""
        self.wm = self.screen.query_one("#desktop", Container).wm
        self.window_offset = self.styles.offset
        self.styles.width, self.styles.height = self.init_width, self.init_height

    def compose(self) -> ComposeResult:
        """Composes the window with a TitleBar and the Executable content."""
        if self.title_bar:
            yield TitleBar(self)
        yield self.executable

    # ┌───────────────────────────────────────────────────────────────────────┐
    # │ Event Handlers                                                        │
    # └───────────────────────────────────────────────────────────────────────┘

    @on(DescendantFocus)
    def on_descendant_focus(self, event: DescendantFocus) -> None:
        """Brings the window to the front when a child is focused (moved to mousedown)."""
        pass

    def _increase_window_size(self, delta: int = 1, direction: str = "right"):
        """Increase or decrease window size in the given direction with min-size safety."""

        def _to_cells(style_value) -> int:
            """Convert any Dimension/Scalar into an absolute cell count."""
            size = self.parent.size if self.parent else self.size
            viewport = self.app.size if self.app else Size(80, 24)
            try:
                return int(round(style_value.resolve(size, viewport)))
            except Exception:
                return int(style_value.value or 0)

        h = _to_cells(self.styles.height)
        w = _to_cells(self.styles.width)
        x = _to_cells(self.styles.offset.x)
        y = _to_cells(self.styles.offset.y)

        def _set_offset(new_x: int, new_y: int):
            self.styles.offset = (new_x, new_y)
            offset = (int(self.styles.offset.x.value), int(self.styles.offset.y.value))
            self.window_offset = offset
            self.user_offset = offset

        if direction == "right":
            new_w = max(self.MIN_WIDTH, w + delta)
            self.styles.width = new_w

        elif direction == "left":
            new_w = max(self.MIN_WIDTH, w + delta)
            shift_x = new_w - (w - delta)
            _set_offset(x + delta - shift_x, y)
            self.styles.width = new_w

        elif direction == "top":
            new_h = max(self.MIN_HEIGHT, h + delta)
            shift_y = new_h - (h - delta)
            _set_offset(x, y + delta - shift_y)
            self.styles.height = new_h

        elif direction == "bottom":
            new_h = max(self.MIN_HEIGHT, h + delta)
            self.styles.height = new_h

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+m":
            self.minimize_window(Button.Pressed(Button("")))  # placeholder
        if event.key == "ctrl+n":
            self.toggle_maximize_window(Button.Pressed(Button("")))
        if event.key == "ctrl+left":
            self._move_window((int(self.styles.offset[0].value) - 1, int(self.styles.offset[1].value)))
        if event.key == "ctrl+right":
            self._move_window((int(self.styles.offset[0].value) + 1, int(self.styles.offset[1].value)))
        if event.key == "ctrl+up":
            self._move_window((int(self.styles.offset[0].value), int(self.styles.offset[1].value) - 1))
        if event.key == "ctrl+down":
            self._move_window((int(self.styles.offset[0].value), int(self.styles.offset[1].value) + 1))
        if event.key == "ctrl+r":
            self.is_window_resizing = not self.is_window_resizing
            self.is_window_dragging = False
            if self.is_window_resizing:
                self.add_class("resize-mode")
            else:
                self.remove_class("resize-mode")
            return

        match event.key:
            case "ctrl+h":
                self._increase_window_size(1, "left")
            case "ctrl+j":
                self._increase_window_size(1, "bottom")
            case "ctrl+k":
                self._increase_window_size(1, "top")
            case "ctrl+l":  # grow rightward
                self._increase_window_size(1, "right")
            case "ctrl+shift+h":  # shrink from left
                self._increase_window_size(-1, "left")
            case "ctrl+shift+j":  # shrink from bottom
                self._increase_window_size(-1, "bottom")
            case "ctrl+shift+k":  # shrink from top
                self._increase_window_size(-1, "top")
            case "ctrl+shift+l":  # shrink from right
                self._increase_window_size(-1, "right")

    def _move_window(self, new_offset: tuple[int, int]) -> None:
        self.user_offset = new_offset
        self.styles.offset = new_offset

    def on_mouse_move(self, event: MouseMove) -> None:
        """Moves the window and record the new user offset"""
        if self.has_class("minimized"):
            return
        if self.is_window_dragging and not self.is_window_resizing:
            new_offset = (
                event.screen_x - self._drag_offset[0],
                event.screen_y - self._drag_offset[1]
            )
            self._move_window(new_offset)
            event.stop()

        elif self.is_window_resizing and self._resize_edge:
            dx = event.screen_x - self._resize_start[0]
            dy = event.screen_y - self._resize_start[1]
            width, height, x, y = self._resize_origin

            if "right" in self._resize_edge:
                self.styles.width = max(self.MIN_WIDTH, width + dx)
            if "left" in self._resize_edge:
                new_width = max(self.MIN_WIDTH, width - dx)
                dx_applied = new_width - (width - dx)
                self.styles.width = new_width
                self.styles.offset = (x + dx - dx_applied, y)
            if "bottom" in self._resize_edge:
                self.styles.height = max(self.MIN_HEIGHT, height + dy)
            if "top" in self._resize_edge:
                new_height = max(self.MIN_HEIGHT, height - dy)
                dy_applied = new_height - (height - dy)
                self.styles.height = new_height
                self.styles.offset = (x, y + dy - dy_applied)

            event.stop()
        elif not self.is_window_dragging:
            self._update_edge_hover_state(*self._get_absolute_local_coords())

    def on_mouse_up(self, event: MouseUp) -> None:
        """Releases the drag lock when the mouse button is released."""
        if self.is_window_dragging:
            self.is_window_dragging = False
            self.release_mouse()
            event.stop()
        if self._resize_edge:
            self._resize_edge = None
            self.release_mouse()
            event.stop

    def on_mouse_down(self, event: MouseDown) -> None:
        if self.is_window_resizing:
            self._resize_edge = None
            for edge, active in (self._last_hover_state or {}).items():
                if active:
                    self._resize_edge = edge
                    break
            if self._resize_edge:
                self.capture_mouse()
                self._resize_start = (event.screen_x, event.screen_y)
                self._resize_origin = (
                    self.styles.width.value,
                    self.styles.height.value,
                    self.styles.offset.x.value,
                    self.styles.offset.y.value,
                )
                event.stop()
        elif self.region.contains(event.screen_x, event.screen_y):
            if self.has_class("minimized"):
                # event.stop()
                return
            self.wm.set_active_window(self)
            # event.stop()

    @on(Leave)
    def on_mouse_leave(self, event: Leave) -> None:
        self._clear_edge_hover_state()
        self._last_hover_state = None

    # ┌───────────────────────────────────────────────────────────────────────┐
    # │ Drag & Resize Logic                                                   │
    # └───────────────────────────────────────────────────────────────────────┘
    def start_drag(self, event: MouseDown) -> None:
        """Initiates a drag operation for the window."""
        if self.is_window_resizing:
            return
        self.is_window_dragging = True
        self._drag_offset = (event.x, event.y)
        self.capture_mouse()

    def _clear_edge_hover_state(self) -> None:
        for side in ("top", "bottom", "left", "right"):
            self.remove_class(f"edge-hover-{side}")

    def _update_edge_hover_state(self, x: int, y: int) -> None:
        """
        Determines which edges are being hovered using LOCAL coordinates
        and applies the correct CSS classes to the widget itself.
        """
        if self.is_window_resizing:
            w, h = self.size

            on_top = 0 <= y < self.EDGE_MARGIN
            on_bottom = h - self.EDGE_MARGIN <= y < h
            on_left = 0 <= x < self.EDGE_MARGIN
            on_right = w - self.EDGE_MARGIN <= x < w

            new_hover_state = {
                "top": on_top, "bottom": on_bottom, "left": on_left, "right": on_right
            }
            if getattr(self, "_last_hover_state", None) == new_hover_state:
                return
            self._last_hover_state = new_hover_state

            self._clear_edge_hover_state()

            if on_top:
                self.add_class("edge-hover-top")
            if on_bottom:
                self.add_class("edge-hover-bottom")
            if on_left:
                self.add_class("edge-hover-left")
            if on_right:
                self.add_class("edge-hover-right")

    # ┌───────────────────────────────────────────────────────────────────────┐
    # │ Watchers & Helpers                                                    │
    # └───────────────────────────────────────────────────────────────────────┘

    def _get_absolute_local_coords(self) -> tuple[int, int]:
        widget_screen_offset = self.screen.get_offset(self)
        widget_screen_region = Region(
            widget_screen_offset.x,
            widget_screen_offset.y,
            self.size.width,
            self.size.height,
        )

        local_x = self.app.mouse_coords[0] - widget_screen_region.x
        local_y = self.app.mouse_coords[1] - widget_screen_region.y
        return (local_x, local_y)

    def get_focusable_elements(self) -> list[Widget]:
        """
        Returns a complete, ordered list of all widgets that can be focused
        within this window, starting with the title bar.
        """
        title_buttons = self.query(PriorityButton).results()
        content_widgets = self._get_focusable_content()
        return list(title_buttons) + content_widgets

    def _get_focusable_content(self) -> list[Widget]:
        """Helper to find all focusable widgets within the Executable."""
        try:
            content_container = self.executable.query_one('#app-content', Widget)
            all_descendants = content_container.query("*")
            return [
                widget for widget in all_descendants
                if widget.can_focus and not widget.disabled
            ]
        except Exception:
            return []

    def watch_window_offset(self, old_offset: tuple[int, int], new_offset: tuple[int, int]) -> None:
        """Syncs the window's offset with its underlying executable."""
        if hasattr(self.executable, 'window_offset'):
            self.executable.window_offset = new_offset

    # ┌───────────────────────────────────────────────────────────────────────┐
    # │ Window Controls                                                       │
    # └───────────────────────────────────────────────────────────────────────┘

    @on(Button.Pressed, "#exit-btn")
    def close_window(self, event: Button.Pressed) -> None:
        log(f"Closing window for {self.executable.app_name}")
        self.app.call_next(self.wm.close_window, self)
        event.stop()

    @on(Button.Pressed, "#minimize-btn")
    def minimize_window(self, event: Button.Pressed) -> None:
        log(f"Minimizing window for {self.executable.app_name}")
        self.wm.handle_window_minimized(self)
        event.stop()

    @on(Button.Pressed, "#maximize-btn")
    def toggle_maximize_window(self, event: Button.Pressed) -> None:
        """Updates internal state and tells the WindowManager to handle the visuals."""
        if not self.is_window_maximized:
            self.window_size = self.size
            self.window_offset = self.styles.offset
        self.wm.handle_window_maximized(self)
        self.is_window_maximized = not self.is_window_maximized
        self.query_one('#maximize-btn').label = glyphs.title_bar["restore"] if self.is_window_maximized else glyphs.title_bar["maximize"]
        event.stop()
