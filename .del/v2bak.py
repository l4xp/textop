"""
A proof-of-concept desktop environment built with the Textual TUI framework.

This application simulates a graphical user interface within the terminal, featuring:
- A window manager with floating and tiling modes.
- Draggable and controllable windows.
- A desktop area, a taskbar, and a clock.
- Basic applications like a Terminal and Notepad.

Project Roadmap:
-----------------
Core Features:
  - [x] Floating, vertical, and horizontal window stacking modes.
  - [x] Dynamic layout switching.
  - [x] Basic terminal application.
  - [ ] Simulated filesystem and OS folder structure (bin, home, etc.).
  - [ ] Installer/setup mode for initial configuration.

Display & UI:
  - [ ] Implement z-axis layering for windows properly.
  - [ ] Custom expandable widgets (e.g., for menus).
  - [ ] Desktop icons for applications.

Window Management:
  - [ ] Workspaces / multiple desktops.
  - [ ] App switcher (e.g., Alt+Tab functionality).

Desktop Features:
  - [ ] Notification/toast system.
  - [ ] Start menu populated from an application directory.
  - [ ] Search functionality.
  - [ ] Advanced applications: File Manager, Image Viewer, Music Player.
  - [ ] Taskbar widgets (battery, volume, etc.).
  - [ ] Screenshot (copy a selection to clipboard)
to continue:
performance optimization on layouts:
    use css layout: grid, horzintal | vertical for quicker change
notepad
terminal
fix de/maximize
fix load/save win pos
no dragging on vstack/hstack
"""
# =============================================================================
# Custom Layout Components (Definitive Version)
# =============================================================================
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from bin.debug import Debug
from bin.notepad import Notepad
from bin.terminal import Terminal
from lib.cascade import Cascade
from lib.executable import Executable
from lib.layout.cascade import CascadeLayout
from textual import log, on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.events import Key, MouseDown, MouseMove, MouseUp
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Static


# =============================================================================
# Window Manager Components
# =============================================================================
class Handle(Static):
    """
    The draggable title bar of a window.

    This component captures mouse events to move its parent `Window` container.
    """
    can_focus = False

    def __init__(self, label: str, id: str | None = None, **kwargs):
        super().__init__(id=id, **kwargs)
        self.label = label

    def compose(self) -> ComposeResult:
        yield Static(self.label, id=self.id)

    async def on_mouse_down(self, event: MouseDown) -> None:
        """Initiates a window drag operation."""
        if self.parent and self.parent.parent:
            window = self.parent.parent  # The grandparent is the Window container.
            log("DRAGGING ENABLED")
            window.dragging = True
            window._mouse_offset_x = event.x
            window._mouse_offset_y = event.y
            window.capture_mouse()
            event.stop()


class Window(Container):
    """
    A container for an application, providing standard window features.

    This includes a title bar, control buttons (minimize, maximize, close),
    and drag-and-drop functionality. It wraps an `Executable` widget.
    """
    window_offset = reactive((0, 0))
    can_focus = True

    def __init__(self, executable: Executable, **kwargs):
        super().__init__(**kwargs)
        self.executable = executable
        self.dragging = False
        self.moved = False
        self.is_window_maximized = False
        self._mouse_offset_x = 0
        self._mouse_offset_y = 0
        self.last_offset_x = self.styles.offset.x.value
        self.last_offset_y = self.styles.offset.y.value
        self.window_offset = (self.styles.offset.x.value, self.styles.offset.y.value)
        self.uuid = f"{uuid4().hex[:6]}"
        log(f"winoff: {self.window_offset}")

    def on_focus(self):
        """When this window gets focus, tell the WindowManager to make it active."""
        self.add_class('active')
        desktop = self.screen.query_one(Desktop)
        desktop.wm.set_active_window(self)

    def compose(self) -> ComposeResult:
        with Horizontal(id="title-bar"):
            yield Handle(f"{self.executable.app_icon}{self.executable.app_name}", id='window-title')
            yield Button("-", id='minimize-btn', compact=True)
            yield Button('൦', id='maximize-btn', compact=True)
            yield Button("✕", id='exit-btn', compact=True)
        yield self.executable

    def on_key(self, event: Key):
        # Notify the WM before removing, so it can manage focus transfer.
        if event.key == "alt+q":
            log(f"removing: {self}")
            desktop = self.screen.query_one(Desktop)
            desktop.wm.handle_window_close(self)
            self.remove()
            event.prevent_default()
        else:
            return

    def on_mouse_up(self, event: MouseUp) -> None:
        """Releases the drag lock when the mouse button is released."""
        if self.dragging:
            self.dragging = False
            self.release_mouse()
            event.stop()

    def on_mouse_move(self, event: MouseMove) -> None:
        """Moves the window if a drag operation is in progress."""
        if self.dragging:
            log(f"Move: window offset = {self.window_offset}")
            self.window_offset = (event.screen_x - self._mouse_offset_x, event.screen_y - self._mouse_offset_y)
            self.styles.offset = self.window_offset
            event.stop()
            self.moved = True

    def watch_window_offset(self, old_offset: tuple[int, int], new_offset: tuple[int, int]) -> None:
        """Syncs the window's offset with its underlying executable."""
        log(f"Window moved to {new_offset}")
        if hasattr(self.executable, 'window_offset'):
            self.executable.window_offset = new_offset

    @on(Button.Pressed, "#exit-btn")
    def close_window(self, event: Button.Pressed) -> None:
        log(f"Closing window for {self.executable.app_name}")
        desktop = self.screen.query_one(Desktop)
        desktop.wm.handle_window_close(self)
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
        log(f"Maximizing/Restoring window for {self.executable.app_name}")
        self.focus()

        if self.is_window_maximized:
            # If maximized, restore to its previous size and position.
            self.reset_styles()
            self.remove_class("maximized")
            self.load_window_position()
            self.query_one('#maximize-btn').label = '൦'
        else:
            # If not maximized, save current position and maximize.
            log(f"Maximizing, window offset_saved = {self.window_offset}")
            self.save_window_position()
            self.add_class("maximized")
            self.styles.offset = (0, 0)
            self.window_offset = (0, 0)  # Update reactive property
            self.query_one('#maximize-btn').label = '⛶'

        self.is_window_maximized = not self.is_window_maximized
        event.stop()

    def save_window_position(self):
        self.last_offset_x = self.window_offset[0]
        self.last_offset_y = self.window_offset[1]

    def load_window_position(self):
        x = self.last_offset_x
        y = self.last_offset_y
        self.window_offset = (x, y)

    def reset_styles(self, mode: str | None = None) -> None:
        """
        Resets dynamic styles or yield to CSS.
        """
        self.styles.width = None
        self.styles.height = None
        self.styles.offset = None
        log(f"Window styles reset: offset={self.window_offset}")


class WindowManager:
    """A utility to manage window layout, creation, and styling on the desktop."""
    def __init__(self, main_desktop_container: Container):
        # A permanent reference to the main Desktop widget.
        self._main_desktop_container = main_desktop_container
        # The currently active container for windows
        self.desktop = main_desktop_container
        self.mode = 'float'
        self.modes = ["float", "vstack", "hstack"]
        self.active_window: Window | None = None

    @property
    def windows(self) -> list[Window]:
        """Returns a list of all managed Window instances."""
        return [child for child in self.desktop.children if isinstance(child, Window)]

    def set_active_window(self, window: Window) -> None:
        """
        Sets the given window as active, handling visual state changes.
        """
        if self.active_window == window:
            return  # It's already active, do nothing.

        log(f"Setting active window to {window.executable.app_name}")
        # Deactivate the old window
        if self.active_window is not None:
            self.active_window.remove_class("active")

        # Activate the new one
        window.add_class("active")
        self.active_window = window

    def handle_window_close(self, closed_window: Window) -> None:
        """Called when a window is about to close."""
        # If the window being closed is the active one, we need to pick a new one.
        if self.active_window == closed_window:
            remaining_windows = [w for w in self.windows if w != closed_window]
            if remaining_windows:
                # Focus the last window in the list as a sensible default.
                # Calling focus() will trigger the on_focus event, which
                # will then call set_active_window().
                remaining_windows[-1].focus()
            else:
                self.active_window = None

    async def sync_window_styles(self) -> None:
        """Applies the current layout mode's class to all active windows."""
        # always call sync last after desktop is set
        for win in self.windows:
            win.remove_class('float', 'vstack', 'hstack')
            win.add_class(self.mode)
            if self.mode == 'float':
                win.load_window_position()
                win.styles.offset = win.window_offset
            elif self.mode == 'cascade':
                self.desktop.styles.layout = CascadeLayout()
            else:
                if win.styles.offset is not None:
                    win.save_window_position()
                win.reset_styles(self.mode)

    async def change_mode(self, mode: str | None = None) -> None:
        """
        Changes the window layout mode and rearranges windows accordingly.

        Args:
            mode: The target mode ('float', 'vstack', 'hstack'). If None, cycles to the next mode.
        """
        # 1. Determine the new mode.
        if mode is None:
            new_mode_index = (self.modes.index(self.mode) + 1) % len(self.modes)
            self.mode = self.modes[new_mode_index]
        else:
            self.mode = mode
        log(f"WindowManager changing mode to: {self.mode}")

        # 2. Capture all existing Window instances.
        old_windows = self.windows

        # 3. If currently in a stacked mode, get the container to be removed.
        old_container_to_remove = None
        if self.desktop != self._main_desktop_container:
            old_container_to_remove = self.desktop

        # 4. Detach windows from the DOM and remove the old layout container.
        for win in old_windows:
            await win.remove()
        if old_container_to_remove:
            await old_container_to_remove.remove()

        # 5. Create a new layout container if needed and update the active desktop.
        self.desktop = self._main_desktop_container
        if self.mode == 'vstack':
            new_container = Vertical(id="vstack-container")
            await self._main_desktop_container.mount(new_container)
            self.desktop = new_container
        elif self.mode == 'hstack':
            new_container = Horizontal(id="hstack-container")
            await self._main_desktop_container.mount(new_container)
            self.desktop = new_container

        # 6. Re-mount windows into the new active container.
        if old_windows:
            await self.desktop.mount_all(old_windows)

        # 7. Apply the correct CSS classes to all windows for the new mode.
        await self.sync_window_styles()

        # 8. Ensure active window is focused
        if self.active_window and self.active_window in self.windows:
            self.active_window.focus()
        elif self.windows:
            self.windows[-1].focus()

    async def spawn_window(self, executable: Executable) -> None:
        """Creates a new window and adds it to the current layout."""
        win = Window(executable)
        win.add_class(self.mode)
        await self.desktop.mount(win)
        win.focus()

    def focus_cycle(self, direction: int = 1) -> None:
        """
        Cycles focus to the next or previous window. Used for Alt+Tab.
        Works in all modes.
        """
        all_windows = self.windows
        if not all_windows:
            return

        current_focus = self.active_window
        try:
            current_index = all_windows.index(current_focus) if current_focus else -1
        except ValueError:
            current_index = -1 # Focused window not in list

        next_index = (current_index + direction + len(all_windows)) % len(all_windows)
        all_windows[next_index].focus()

    def focus_direction(self, direction: str) -> None:
        """
        Moves focus directionally. Only works in tiling modes.
        """
        if self.mode == 'float':
            return

        direction_map = {
            'vstack': {'up': -1, 'down': 1},
            'hstack': {'left': -1, 'right': 1},
        }

        if self.mode not in direction_map or direction not in direction_map[self.mode]:
            return # trying to move 'left' in 'vstack'

        cycle_dir = direction_map[self.mode][direction]
        self.focus_cycle(cycle_dir)

# =============================================================================
# Custom Messages
# =============================================================================


class Run(Message):
    """A message to request opening a new application window."""
    def __init__(self, executable: Executable):
        log(f"Posting request to run {executable.app_name}.")
        self.executable = executable
        super().__init__()


class ChangeWindowMode(Message):
    """A message to request a change in the window layout mode."""
    def __init__(self, mode: str):
        log(f"Posting request to change window mode to {mode}.")
        self.mode = mode
        super().__init__()


# =============================================================================
# Applications on termos/bin/
# =============================================================================


# =============================================================================
# Main UI Components
# =============================================================================

class Desktop(Container):
    """
    The main workspace container for the user.

    It holds all windows and the background layer and uses a WindowManager
    to handle window layout and behavior.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.wm = WindowManager(self)

    def compose(self) -> ComposeResult:
        yield Container(id='background')

    def on_mount(self) -> None:
        """Initializes the WindowManager for this desktop.""" # moved to init
        pass

    @on(ChangeWindowMode)
    async def on_change_window_mode(self, message: ChangeWindowMode) -> None:
        """Handles requests to change the window layout mode."""
        log(f"Desktop received ChangeWindowMode to {message.mode}")
        await self.wm.change_mode(message.mode)


class Taskbar(Horizontal):
    """The bottom taskbar with application launchers and widgets."""
    def compose(self) -> ComposeResult:
        with Horizontal(id="left-taskbar"):
            yield Button("⌘ Start", id="start-button", compact=True)
        with Horizontal(id="center-taskbar"):
            yield Button("🖳 Terminal", id="btn-terminal", compact=True)
            yield Button("⏍ Notepad", id="btn-notepad", compact=True)
            yield Button("Debug", id="btn-debug", compact=True)
        with Horizontal(id="right-taskbar"):
            yield WMLayout()
            yield Clock()

    @on(Button.Pressed, "#btn-notepad")
    def open_notepad(self):
        self.post_message(Run(Notepad()))

    @on(Button.Pressed, "#btn-terminal")
    def open_terminal(self):
        self.post_message(Run(Terminal()))

    @on(Button.Pressed, "#btn-debug")
    def open_debug(self):
        self.post_message(Run(Debug()))


class WMLayout(Widget):
    """A live digital clock widget for the taskbar."""
    text = reactive("")

    def on_mount(self) -> None:
        """Updates the time every second."""
        self.update_text()
        self.set_interval(1.0, self.update_text)

    def update_text(self) -> None:
        desktop = self.parent.parent.parent.query_one(Desktop)  # type: ignore[union-attr]
        self.text = f"|{desktop.wm.mode}|"

    def render(self) -> str:
        self.styles.width = len(self.text)
        return self.text


class Clock(Widget):
    """A live digital clock widget for the taskbar."""
    time = reactive("")

    def on_mount(self) -> None:
        """Updates the time every second."""
        self.update_time()
        self.set_interval(1.0, self.update_time)

    def update_time(self) -> None:
        """Sets the time reactive property to the current time."""
        self.time = datetime.now().strftime("%I:%M %p")

    def render(self) -> str:
        text = f" ⏲ {self.time} "
        self.styles.width = len(text)
        return text


# =============================================================================
# Main Application
# =============================================================================

class Termos(App):
    """
    The main Textual application.

    This class orchestrates the entire desktop environment, including the
    desktop, taskbar, global key bindings, and event handling.
    """
    CSS_PATH = "main.css"
    BINDINGS = [
        ("alt+tab", "cycle_focus", "Cycle Window Focus"),
        ("alt+j", "focus_direction('down')", "Focus Down"),
        ("alt+k", "focus_direction('up')", "Focus Up"),
        ("alt+h", "focus_direction('left')", "Focus Left"),
        ("alt+l", "focus_direction('right')", "Focus Right"),
        ("alt+c", "cycle_window_mode", "Cycle Layout"),
        ("alt+enter", "sys_run('Terminal')", "Open Terminal"),
        ("alt+n", "sys_run('Notepad')", "Open Notepad")
    ]

    def compose(self) -> ComposeResult:
        yield Desktop(id="desktop")
        yield Taskbar(id="taskbar")

    @on(Run)
    async def on_run(self, message: Run) -> None:
        """Handles Run messages to spawn new application windows."""
        log(f"App received Run message for {message.executable.app_name}")
        desktop = self.query_one(Desktop)
        await desktop.wm.spawn_window(message.executable)

    def action_sys_run(self, app_widget: str):
        match app_widget:
            case "Terminal":
                self.post_message(Run(Terminal()))
            case "Notepad":
                self.post_message(Run(Notepad()))

    async def action_cycle_window_mode(self) -> None:
        """Cycles through the available window layout modes."""
        log("App action: Cycling window mode.")
        desktop = self.query_one(Desktop)
        await desktop.wm.change_mode()

    def action_focus_direction(self, direction: str) -> None:
        """Moves focus in a specific direction in tiling modes."""
        log(f"App action: Focusing direction {direction}.")
        desktop = self.query_one(Desktop)
        desktop.wm.focus_direction(direction)

    async def action_cycle_focus(self):
        log("its happening")
        desktop = self.query_one(Desktop)
        desktop.wm.focus_cycle()

    async def on_mouse_move(self, event: MouseMove) -> None:
        """Handles global mouse movement to pipe info to the Debug app."""
        # Find the Debug app instance, if it exists.
        debug_app = next((w.executable for w in self.query(Window) if isinstance(w.executable, Debug)), None)
        if not debug_app:
            return

        widget_under_mouse, _ = self.screen.get_widget_at(event.screen_x, event.screen_y)
        widget_id = getattr(widget_under_mouse, 'id', 'N/A')
        widget_class = widget_under_mouse.__class__.__name__ if widget_under_mouse else "None"

        info_text = (
            f"Mouse (Global): X={event.screen_x}, Y={event.screen_y}\n"
            f"Widget Below: {widget_class} (ID: {widget_id})"
        )
        debug_app.content_label.update(info_text)


if __name__ == "__main__":
    Termos().run()
