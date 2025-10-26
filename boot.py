"""
textop v0.3
A desktop environment simulator on terminal
Built with Textual v3.7.0

This application simulates a graphical user interface within the terminal, featuring:
- A window manager with floating and tiling modes.
- A status bar, start menu, and widgets
- A small suite of applications
- Mouse & keyboard navigation

Project Roadmap:
-----------------
Core Features:
  - [x] Dynamic Layouts (float, vstack, hstack, uwide, bsp)
  - [x] Basic Window Management (open, minimize, maximize, close, move, resize, layout)
  - [x] Core apps & Executables(notepad, calculator, terminal, browser, media viewer, browser)
  - [x] Status bar
  - [ ] Installer/setup mode for initial configuration.
  - [ ] Simulated filesystem and OS folder structure (bin, home, etc.).

Display & UI:
  - [X] Implement layering for windows properly.
  - [?] Custom expandable widgets (e.g., for menus).
  - [ ] Desktop icons for applications.
  - [ ] Animations?

Window Management:
  - [ ] Workspaces / multiple desktops.
  - [X] App switcher (Alt+Tab functionality).
  - [X] Window states
  - [ ] Workspaces

Desktop Features:
  - [X] Notification/toast system.
  - [ ] Start menu populated from an application directory.
  - [ ] Search functionality.
  - [ ] Advanced applications: File Manager, Image Viewer, Music Player.
  - [ ] Screenshot (copy a selection to clipboard)

Taskbar Features:
  - [ ] Taskbar widgets (battery, volume, etc.).
  - [ ] Active Window feedback + switcher

QOL:
  - [ ] yaml/toml config for taskabr
  - [ ] Somehow safely expose non-crucial desktop css for users / not?
  - [ ] json for state persistence??
  - [X] glyphs module for centralized font shennanigans
  - [ ] mod + drag to move windows
  - [ ] css var with classes for dynamically styling borders (ascii,panel,full)


MISC DONE:
- better layout swiching performance (only css now)
- notepad
- fix de/maximize
- fix load/save win pos (offset)
- no dragging on vstack/hstack
- fix maximize not working on active window
- initial window jump on drag, no longer
- terminal -> custom string parsing + vfs (to separate)
- fix dummy exit
- impl. minimize
- impl. resize windows via keys
- windows fix
- keypress toast

CONTINUE:
taskbar
VFS

TODO PRIO
- taskbar
- vfs
- workspace
- user system

|--------------------|
| Settings      - + x|
|--------------------|
| Windows            |
| A |````````````````|
| B | [ |x] Borders  |
| C | [o| ] TitleBar |
| D |                |
| E |                |
| F |                |
|--------------------|

"""
from __future__ import annotations

from typing import Dict, Set, Tuple, cast

import lib.display.glyphs as glyphs
from bin.debug import Debug, DebugContent
from bin.notepad import Notepad
from bin.terminal import Dustty
from lib.core.events import ActiveWindowsChanged, Run
from lib.core.widgets import UIToast
from lib.debug2 import DomInfoOverlay
from lib.display.bar import Taskbar
from lib.display.window import Window
from lib.display.wm import Desktop
from textual import log, on, timer
from textual._border import BORDER_CHARS, BORDER_LOCATIONS
from textual.app import App, ComposeResult, Timer
from textual.containers import Container
from textual.css.constants import VALID_BORDER
from textual.events import MouseMove
from textual.geometry import Offset, Region
from textual.reactive import reactive
from textual.widgets import Label

# =============================================================================
# Textual Patch
# =============================================================================
BorderCharsType = Tuple[Tuple[str, str, str], Tuple[str, str, str], Tuple[str, str, str]]
BorderLocationsType = Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]

FULL_BORDER: Dict[str, BorderCharsType] = {
    "full": (
        ("🭽", "▔", "🭾"),
        ("▏", " ", "▕"),
        ("🭼", "▁", "🭿"),
    )
}
FULL_BORDER_LOCATIONS: Dict[str, BorderLocationsType] = {
    "full": ((0, 0, 0), (0, 0, 0), (0, 0, 0)),
}

cast(Dict[str, BorderCharsType], BORDER_CHARS).update(FULL_BORDER)
cast(Dict[str, BorderLocationsType], BORDER_LOCATIONS).update(FULL_BORDER_LOCATIONS)
cast(Set[str], VALID_BORDER).update(FULL_BORDER.keys())
# =============================================================================
# Main Application
# =============================================================================
class TextTop(App):
    """
    This class orchestrates the entire desktop environment, including the
    desktop, taskbar, global key bindings, and event handling.
    """
    CSS_PATH = "main.css"
    BINDINGS = [
        ("alt+tab", "cycle_focus('1')", "Cycle Window Focus Up"),
        ("alt+shift+tab", "cycle_focus('-1')", "Cycle Window Focus Down"),
        ("alt+j", "focus_direction('down')", "Focus Down"),
        ("alt+k", "focus_direction('up')", "Focus Up"),
        ("alt+h", "focus_direction('left')", "Focus Left"),
        ("alt+l", "focus_direction('right')", "Focus Right"),
        ("alt+c", "cycle_window_mode", "Cycle Layout"),
        ("alt+enter", "sys_run('Terminal')", "Open Terminal"),
        ("alt+n", "sys_run('Notepad')", "Open Notepad"),
        ("f12", "toggle_dom_inspector", "Toggle DOM Inspector"),
        ("ctrl+f12", "pause_dom_inspector", "Pause Inspector"),
        ("alt+q", "sys_kill()", "")
    ]
    mouse_coords = (0, 0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.toast = UIToast()
        self.hide_toast_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield self.toast
        yield Desktop(id="desktop")
        yield Taskbar(id="taskbar")
        yield DomInfoOverlay(id="dom_info_overlay")

    def on_key(self, event):
        # keys = [key[0] for key in self.BINDINGS]
        # if event.key in keys:
        self.show_keypress(f"{event.key}")

    def on_mount(self) -> None:
        self.wm = self.query_one(Desktop).wm

    def show_keypress(self, message: str, timeout: float = 1.5):
        self.toast.show(message)

        if self.hide_toast_timer:
            self.hide_toast_timer.stop()

        self.hide_toast_timer = self.set_timer(timeout, self.toast.hide)

    @on(ActiveWindowsChanged)
    def update_taskbar(self, message: ActiveWindowsChanged):
        self.query_one(Taskbar).update_active_windows(message)

    @on(Run)
    async def on_run(self, message: Run) -> None:
        """Handles Run messages and spawn new application windows."""
        log(f"App received Run message for {message.executable.app_name}")
        desktop = self.query_one(Desktop)
        await desktop.wm.spawn_window(message.executable)

    def action_sys_run(self, app_widget: str):
        match app_widget:
            case "Terminal":
                self.post_message(Run(Dustty()))
            case "Notepad":
                self.post_message(Run(Notepad()))

    def action_sys_kill(self, window: None | Window = None):
        """Kills the specified | active window."""
        log(f"Attempt: kill {window}.")
        target_window = self.wm.active_window if window is None else window
        if target_window:
            self.call_next(self.wm.close_window, target_window)
        else:
            log("sys_kill failed: No active window to kill.")

    async def action_cycle_window_mode(self) -> None:
        """Cycles through the available window layout modes."""
        log("App action: Cycling window mode.")
        self.wm.change_mode()

    def action_focus_direction(self, direction: str) -> None:
        """Moves focus in a specific direction in tiling modes."""
        log(f"App action: Focusing direction {direction}.")
        desktop = self.query_one(Desktop)
        desktop.wm.focus_direction(direction)

    async def action_cycle_focus(self, direction: str):
        log(f"App action: cycling focus {'next' if direction == 1 else 'previous'}.")
        self.wm.focus_cycle(int(direction))

    def action_pause_dom_inspector(self) -> None:
        """Action to pause or resume the DOM inspector's movement."""
        overlay = self.query_one(DomInfoOverlay)
        overlay.pause(not overlay._is_paused)

    def action_toggle_dom_inspector(self) -> None:
        """Action to toggle the DOM information overlay."""
        overlay = self.query_one(DomInfoOverlay)
        overlay.toggle_visibility()

    async def on_mouse_move(self, event: MouseMove) -> None:
        self.mouse_coords = (event.screen_x, event.screen_y)
        overlay = self.query_one(DomInfoOverlay)
        if overlay.is_visible:
            widget_under_mouse_local, _ = self.get_widget_at(event.x, event.y)
            target = widget_under_mouse_local or self.focused
            if target and target is not overlay and overlay not in target.ancestors:
                overlay.update_and_position(event.x, event.y, target)

        debug_executable = next((w for w in self.query(Debug)), None)
        if not debug_executable:
            return

        debug_content_widget = debug_executable.query_one(DebugContent)

        widget_under_mouse = event.control

        info_text = (
            f"--- Mouse Info ---\n"
            f"Global (screen): ({event.screen_x}, {event.screen_y})\n"
            f"Local (app):   ({event.x}, {event.y})\n"
        )

        if widget_under_mouse and widget_under_mouse.is_mounted:
            widget_size = widget_under_mouse.size

            widget_screen_offset = self.screen.get_offset(widget_under_mouse)
            widget_screen_region = Region(
                widget_screen_offset.x,
                widget_screen_offset.y,
                widget_size.width,
                widget_size.height,
            )

            widget_local_x = event.screen_x - widget_screen_region.x
            widget_local_y = event.screen_y - widget_screen_region.y

            info_text += (
                f"\n--- Widget Under Mouse (from event.control) ---\n"
                f"Class: {widget_under_mouse.__class__.__name__}\n"
                f"ID: {getattr(widget_under_mouse, 'id', 'N/A')}\n"
                f"Region (parent): {widget_under_mouse.region}\n"
                f"Region (screen): {widget_screen_region}\n"
                f"Mouse (widget):  ({widget_local_x}, {widget_local_y})\n"
                f"Offset Style: {widget_under_mouse.styles.offset}\n"
                f"Mounted: {widget_under_mouse.is_mounted}"
            )

            last_widget = getattr(self, "_last_debug_widget", None)
            if widget_under_mouse is not last_widget:
                self.log.info(f"--- Hover Changed ---")
                self.log.info(f"Mouse looking at {widget_under_mouse} via event.control")
                self._last_debug_widget = widget_under_mouse

        else:
            info_text += "\n--- Widget Under Mouse ---\nNone"
            self._last_debug_widget = None

        debug_content_widget.update_info(info_text)


if __name__ == "__main__":
    glyphs.init("compatible")
    TextTop().run()
