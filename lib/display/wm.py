from lib.core.events import ActiveWindowsChanged
from lib.display.flyout import Flyout
from lib.display.layout import *
from lib.display.window import Executable, PriorityButton, Window
from textual import log
from textual.app import ComposeResult
from textual.containers import Container
from textual.message import Message
from textual.reactive import reactive
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Label


class Desktop(Container):
    """
    The main workspace container for the user.

    It holds all windows and the background layer with a WindowManager
    to handle window layout and behavior.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.wm = WindowManager(self, mode='float')

    async def on_mount(self) -> None:
        """Tell the WindowManager to mount its persistent container."""
        await self.wm.on_mount()


class WMLayout(Widget):
    """Window manager layout UI widget."""
    text = reactive("", layout=True)

    def on_mount(self) -> None:
        """When mounted, get the initial state from the WindowManager."""
        wm = self.app.query_one(Desktop).wm
        self.text = f"  {wm.mode}  "

    def update_mode(self, new_mode: str) -> None:
        """A public method to directly update the layout text."""
        print(f"WMLayout received direct update: {new_mode}")
        self.text = f"  {new_mode}  "

    def render(self) -> str:
        return self.text

    def watch_text(self, new_text: str) -> None:
        """When the text changes, automatically update the widget's width."""
        self.styles.width = len(new_text)


class WindowManager:
    """
    A utility to manage window layout, creation, and styling on the desktop.
    """
    def __init__(self, desktop_layer: Desktop, mode: str = 'float'):
        # mounts a single dynamically set container
        self.window_container = Container(id="window-container")
        self._desktop_layer = desktop_layer
        self.mode = mode
        self.modes = ["float", "vstack", "hstack", "bsp", "bsp_alt", "ultra_wide", "ultra_tall"]
        self.active_window: Window | None = None
        self.active_flyout: Flyout | None = None

    async def on_mount(self):
        await self._desktop_layer.mount(self.window_container)
        self.change_mode(self.mode, initial=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Window Management
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def windows(self) -> list[Window]:
        """Returns a list of all managed Window instances."""
        return [child for child in self.window_container.children if isinstance(child, Window)]

    async def spawn_window(self, executable: Executable) -> None:
        """Creates a new window and adds it to the container."""
        def _center_window(window):
            parent_size = self.window_container.size
            window_size = (window.init_width, window.init_height)
            offset_x = (parent_size.width - window_size[0]) // 2
            offset_y = (parent_size.height - window_size[1]) // 2
            window.styles.offset = (offset_x, offset_y)
            window.user_offset = (offset_x, offset_y)

        win = Window(executable)
        self._apply_styles_for_window(win)
        _center_window(win)
        await self.window_container.mount(win)
        self.set_active_window(win)
        self._post_active_windows_update()

    async def close_window(self, window_to_close: Window) -> None:
        """The authoritative method for closing a window safely."""
        if not window_to_close.parent: return

        remaining_windows = [w for w in self.windows if w is not window_to_close and not w.has_class("minimized")]
        next_focus_target = remaining_windows[-1] if remaining_windows else None

        self.window_container.screen.set_focus(None)

        if next_focus_target:
            self.set_active_window(next_focus_target)
        else:
            self.active_window = None

        await window_to_close.remove()
        self._post_active_windows_update()

    def handle_window_maximized(self, window: Window) -> None:
        """Applies/removes the maximized class based on window state."""
        # if already maximized
        if window.is_window_maximized:
            window.remove_class("maximized")
            if self.mode == 'float':
                window.styles.offset = window.window_offset
                window.styles.width, window.styles.height = window.window_size
        else:
            window.add_class("maximized")
            window.styles.width = None
            window.styles.height = None
            window.styles.offset = None

    def handle_window_minimized(self, window: Window) -> None:
        window.add_class("minimized")
        remaining_windows = [w for w in self.windows if w is not window and not w.has_class("minimized")]
        next_focus_target = remaining_windows[-1] if remaining_windows else None
        if next_focus_target:
            self.set_active_window(next_focus_target)
        else:
            self.active_window = None

    def set_active_window(self, window: "Window") -> None:
        """Sets the active window, applies CSS, and focuses its content."""
        if self.active_window is window:
            # window.executable.focus_content()
            return

        if self.active_window:
            self.active_window.remove_class("active")

        window.add_class("active")
        window.remove_class("minimized")
        self.active_window = window
        window.executable.focus_content()

    def _apply_styles_for_window(self, win: Window):
        """Applies mode-specific classes and styles to a single window."""
        self.window_container.remove_class(*self.modes)
        self.window_container.add_class(self.mode)
        win.remove_class(*self.modes)
        win.add_class(self.mode)

        if self.mode == 'float':
            win.styles.offset = win.user_offset
        else:
            win.styles.offset = None

    def cycle_focus_element(self, direction: int = 1) -> None:
        """Cycles focus between focusable ELEMENTS within the active window"""
        if not self.active_window:
            return
        focusable_elements = self.active_window.get_focusable_elements()
        if not focusable_elements:
            return
        currently_focused = self.window_container.app.screen.focused
        try:
            current_index = focusable_elements.index(currently_focused)
        except ValueError:
            current_index = -1
        next_index = (current_index + direction) % len(focusable_elements)
        focusable_elements[next_index].focus()

    def focus_cycle(self, direction: int = 1) -> None:
        """Cycles the active window and focuses its content."""
        all_windows = self.windows
        if not all_windows or not self.active_window:
            return

        try:
            current_index = all_windows.index(self.active_window) if self.active_window else -1
        except ValueError:
            current_index = -1

        next_index = (current_index + direction) % len(all_windows)
        self.set_active_window(all_windows[next_index])

    def _get_visual_neighbor(self, direction: str) -> Window | None:
        """
        Ask the current layout for the visual neighbor of the active window.
        Returns None if no neighbor exists or layout doesn't support directional navigation.
        """
        if not self.active_window:
            return None

        layout = self.window_container.styles.layout
        if layout and hasattr(layout, "get_neighbor"):
            return layout.get_neighbor(self.active_window, direction)
        return None

    def focus_direction(self, direction: str) -> None:
        """
        Move focus in a given direction using layout-aware neighbors.
        """
        if not self.active_window or self.mode == 'float':
            return

        neighbor = self._get_visual_neighbor(direction)
        if neighbor:
            self.set_active_window(neighbor)
            return

        print("No neighbor found")

    def move_window_direction(self, direction: str) -> None:
        """
        Move the active window in a given direction.
        """
        if not self.active_window or self.mode == 'float':
            return

        neighbor = self._get_visual_neighbor(direction)
        if neighbor:
            if direction in ["up", "left"]:
                self.window_container.move_child(self.active_window, before=neighbor)
            elif direction in ["down", "right"]:
                self.window_container.move_child(self.active_window, after=neighbor)
            return

        print("No neighbor found")

    def _post_active_windows_update(self) -> None:
        """Helper method to calculate and post the window state."""
        new_active_windows: dict[str, list] = {}
        for window in self.windows:
            app_id = window.executable.APP_ID
            if app_id not in new_active_windows:
                new_active_windows[app_id] = []
            new_active_windows[app_id].append(window)

        self.window_container.post_message(ActiveWindowsChanged(new_active_windows))

    # ─────────────────────────────────────────────────────────────────────────
    # Flyout Management
    # ─────────────────────────────────────────────────────────────────────────

    async def request_flyout(self, new_flyout: Flyout) -> None:
        """
        Handles a request to show a flyout, ensures only one is active at a time.
        """
        if self.active_flyout is not None:
            is_toggling_same_flyout = (self.active_flyout.id == new_flyout.id)
            await self.close_active_flyout()

            if is_toggling_same_flyout:
                return

        self.active_flyout = new_flyout
        await self._desktop_layer.mount(self.active_flyout)
        self.active_flyout.focus()

    async def close_active_flyout(self):
        flyouts = self._desktop_layer.app.query(Flyout)
        if not flyouts:
            return
        self.window_container.screen.set_focus(None)
        await flyouts.remove()
        self.active_flyout = None

    # ─────────────────────────────────────────────────────────────────────────
    # Layout Management
    # ─────────────────────────────────────────────────────────────────────────

    def change_mode(self, mode: str | None = None, initial: bool = False) -> None:
        """Changes the layout mode by setting the style on window container."""
        # default
        if not initial:
            self.mode = self.modes[(self.modes.index(self.mode) + 1) % len(self.modes)]
        else:
            self.mode = mode or 'float'

        layout_map = {
            'float': None,
            'vstack': VerticalStackLayout(),
            'hstack': HorizontalStackLayout(),
            'bsp': BSPLayout(),
            'bsp_alt': BSPAltLayout(),
            'ultra_wide': UltrawideLayout(),
            'ultra_tall': UltratallLayout(),
        }

        self.window_container.styles.layout = layout_map.get(self.mode)

        # Apply classes for styling
        self.window_container.remove_class(*self.modes)
        self.window_container.add_class(self.mode)

        # Update styles for all existing windows
        for win in self.windows:
            self._apply_styles_for_window(win)

        # Integration for taskbar widget
        try:
            wmlayout_widget = self.window_container.app.screen.query_one(WMLayout)
            wmlayout_widget.update_mode(self.mode)
        except Exception:
            log.warning("WMLayout widget not found, can't update display.")
