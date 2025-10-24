from lib.display.layout import *
from lib.display.window import Executable, Window
from textual import log
from textual.containers import Container
from textual.reactive import reactive
from textual.widget import Widget


"""
Alt tab - temp view of instance

+-----------------------------+
|                             |
|          +---- x +          |
|          |       |          |
|          +-------+          |
|                             |
+-----------------------------+
"""


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
        self.text = f"|{wm.mode}|"

    def update_mode(self, new_mode: str) -> None:
        """A public method to directly update the layout text."""
        log(f"WMLayout received direct update: {new_mode}")
        self.text = f"|{new_mode}|"

    def render(self) -> str:
        return self.text

    def watch_text(self, new_text: str) -> None:
        """When the text changes, automatically update the widget's width."""
        self.styles.width = len(new_text)


class WindowManager:
    """A utility to manage window layout, creation, and styling on the desktop. Should be the only class that decides who should be active. """
    """
    Layout Modes:
    float: no layout, let each window handle their own styles/layout, newest spawns centered
        - draggin enabled
        - change focus with alt+tab
        - saves window offset
    vstack: arrange children stacked vertically, newest spawns below
        - no dragging
        - change focus with j, k
    hstack: arrange children stacked horizontally, newest spawns to the right
        - no dragging
        - change focus with h, l
    cascade: arrange children overlayed, offset 2 to the right and 1 below, newest spawn center layered
        - no dragging ?
        - change focus with alt+tab
        - active window retain previous inactive window position
        - move window to previous layout chiildren index when active >> inactive
    traditional cascade + float (unimplemented)
        - dragging enabled
        - change focus with alt+tab
        - spawn offset * active_windows length
        - let windows handle styles afterward
    ultra-wide stack:
        - no dragging
        - change mode with h, j, k, l
        - spawn: 1) center-maximized, 2) horizontal-split, 3) %width: 25% left | 50% center | 25% right, 4..n) 25% left | 50% center | 25% vertical-stack-split right
    bsp:
        - recursive horizontal / vertical split of last child layout
        - no dragging
        - change focus with h, j, k, l
    """
    def __init__(self, desktop_layer: Desktop, mode: str = 'float'):
        # mounts a single dynamically set container
        self.window_container = Container(id="window-container")
        self._desktop_layer = desktop_layer
        self.mode = mode
        self.modes = ["float", "vstack", "hstack", "bspV", 'ultraT']
        self.active_window: Window | None = None

    async def on_mount(self):
        await self._desktop_layer.mount(self.window_container)
        self.change_mode(self.mode, initial=True)

    @property
    def windows(self) -> list[Window]:
        """Returns a list of all managed Window instances."""
        return [child for child in self.window_container.children if isinstance(child, Window)]

    def _get_next_window_for_focus(self, closed_window: Window) -> Window | None:
        """Helper to find the next window to focus when one is closed."""
        if self.active_window == closed_window:
            # Get a list of windows that are NOT the one being closed.
            remaining_windows = [
                w for w in self.window_container.query(Window) if w is not closed_window
            ]
            if remaining_windows:
                # Return the last window in the list as the next focus target.
                return remaining_windows[-1]  # this should be the last ACTIVE window in the list instead
        return None

    async def close_window(self, window_to_close: "Window") -> None:
        """The authoritative method for closing a window safely."""
        # the dummy trick should be unneccesary now, since the DescendantFocus should be the culprit for the flicker bug
        window_to_close.add_class("terminated")
        if not window_to_close.parent: return

        remaining_windows = [w for w in self.windows if w is not window_to_close]
        next_focus_target = remaining_windows[-1] if remaining_windows else None

        if next_focus_target:
            self.set_active_window(next_focus_target)
        else:
            self.active_window = None

        await window_to_close.remove()

    def handle_window_maximized(self, window: Window) -> None:
        """Applies/removes the maximized class based on window state."""
        # if TO BE maximimized
        if window.is_window_maximized:
            window.add_class("maximized")
            window.styles.offset = None
        else:
            window.remove_class("maximized")
            if self.mode == 'float':
                window.styles.offset = window.window_offset

    def change_mode(self, mode: str | None = None, initial: bool = False) -> None:
        """Changes the layout mode by setting the style on window container."""
        # default
        if not initial:
            self.mode = self.modes[(self.modes.index(self.mode) + 1) % len(self.modes)]
        else:
            self.mode = mode or 'float'

        layout_map = {
            'float': None,
            'vstack': TiledVerticalLayout(),
            'hstack': TiledHorizontalLayout(),
            # 'cascade': CascadeLayout(),
            # 'bspL': BSPLargestLayout(),
            'bspV': VerticalBSPSpiralLayout(),
            'ultraT': UltratallLayout(),
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

    def handle_window_minimized(self, window: Window) -> None:
        window.add_class("minimized")
        remaining_windows = [w for w in self.windows if w is not window]
        next_focus_target = remaining_windows[-1] if remaining_windows else None
        if next_focus_target:
            self.set_active_window(next_focus_target)
        else:
            self.active_window = None

    def set_active_window(self, window: "Window") -> None:
        """Sets the active window, applies CSS, and focuses its content."""
        if self.active_window is window: return
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

    async def spawn_window(self, executable: Executable) -> None:
        """Creates a new window and adds it to the container."""
        win = Window(executable)
        self._apply_styles_for_window(win)
        await self.window_container.mount(win)
        self.set_active_window(win)

    def focus_cycle(self, direction: int = 1) -> None:
        """Cycles the active window and focuses its content."""
        all_windows = self.windows
        if not all_windows:
            return

        try:
            current_index = all_windows.index(self.active_window) if self.active_window else -1
        except ValueError:
            current_index = -1

        next_index = (current_index + direction) % len(all_windows)
        self.set_active_window(all_windows[next_index])

    def focus_direction(self, direction: str) -> None:
        """
        Moves focus directionally. Only works in tiling layouts.
        """
        if self.mode == 'float':
            return

        direction_map = {
            'vstack': {'up': -1, 'down': 1},
            'hstack': {'left': -1, 'right': 1},
        }

        if self.mode not in direction_map or direction not in direction_map[self.mode]:
            return  # trying to move 'left' in 'vstack'

        cycle_dir = direction_map[self.mode][direction]
        self.focus_cycle(cycle_dir)
