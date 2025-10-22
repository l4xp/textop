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
  - [ ] Notification/toast system.
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

CONTINUE:
VFS

TODO PRIO
- minimize / restore
- taskbar
- window resizing
- notif toast (key toast)
- vfs
- workspace
- user system

TO FIX:
- dummy exit trick looks annoying

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
from lib.core.events import Run
from lib.debug2 import DomInfoOverlay
from lib.display.bar import Taskbar
from lib.display.window import Window
from lib.display.wm import Desktop
from textual import log, on
from textual._border import BORDER_CHARS, BORDER_LOCATIONS
from textual.app import App, ComposeResult
from textual.css.constants import VALID_BORDER
from textual.events import MouseMove

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

    def compose(self) -> ComposeResult:
        yield Desktop(id="desktop")
        yield Taskbar(id="taskbar")
        yield DomInfoOverlay(id="dom_info_overlay")

    def on_mount(self) -> None:
        self.wm = self.query_one(Desktop).wm

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
        # debug app overlay
        overlay = self.query_one(DomInfoOverlay)

        if overlay.is_visible:
            widget_under_mouse, _ = self.get_widget_at(event.x, event.y)
            target = widget_under_mouse or self.focused

            if target and target is not overlay and overlay not in target.ancestors:
                overlay.update_and_position(event.x, event.y, target)

        # debug app taskbar
        debug_executable = next((w for w in self.query(Debug)), None)
        if debug_executable:
            debug_content_widget = debug_executable.query_one(DebugContent)

            widget_under_mouse, _ = self.screen.get_widget_at(event.screen_x, event.screen_y)
            widget_id = getattr(widget_under_mouse, 'id', 'N/A')
            widget_class = widget_under_mouse.__class__.__name__ if widget_under_mouse else "None"

            info_text = (
                f"Mouse (Global): X={event.screen_x}, Y={event.screen_y}\n"
                f"Widget Below: {widget_class} (ID: {widget_id})"
            )
            debug_content_widget.update_info(info_text)


if __name__ == "__main__":
    glyphs.init("compatible")
    TextTop().run()
