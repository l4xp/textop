"""
textop v0.5
A desktop environment simulator on terminal
Built with Textual v6.5.0

This application simulates a graphical user interface within the terminal, featuring:
- A window manager with floating and tiling modes.
- A status bar, start menu, and widgets
- A small suite of applications
- Mouse & keyboard navigation

Project Roadmap:
-----------------
General System & Display:
  - [~] Windows z-levels (layers)
  - [X] Popup/expandable mini windows (flyouts system)
  - [~] Desktop icons for applications (glyphs system)
  - [ ] Installer/setup mode for initial configuration
  - [ ] Animations? (heavy)
  - [~] Simulated filesystem and OS folder structure (bin, home, etc.) (vfs)

Window Management:
  - [ ] Workspaces / multiple desktops
  - [x] Window Basics (open, minimize, maximize, close, move, resize)
  - [X] App switcher (Alt+Tab / activewindowlist)
  - [X] Window states (runtime)
  - [ ] Window states (memory)
  - [x] Dynamic Layouts (float, vstack, hstack, uwide, utall, bsp, bsp_alt)

Desktop:
  - [X] Notification/toast system
  - [ ] State persistence (snapshots)
  - [ ] User system (login/logout/switch/create/delete)
  - [ ] Security (privileges, passwords, encrypt, decrypt system, hide/show)
  - [ ] Global 'cursor', kb/mouse controlled

Status Bar:
  - [x] Launchers (terminal, notepad, debug)
  - [ ] Dynamic launcher pinning
  - [X] Taskbar widgets (battery, volume, etc.)
  - [X] Active Window feedback + switcher
  - [X] Start menu populated from an application directory
  - [~] Start Menu
  - [ ] Search functionality

Apps:
  - [x] notepad, terminal/s, snake game
  - [ ] calculator, browser, media viewer/player, file manager, settings

QOL:
  - [ ] Screenshot (copy a selection to clipboard)
  - [ ] Module-specific configs (taskbar, windows, wm)
  - [ ] CSS override configs (taskbar, windows, wm, desktop)

Compatibility:
  - [ ] Command Pallette (in place of hotkeys)
  - [ ] Use Ctrl+[A-Z, @], Enter, Esc, Tab, Backspace, Arrow keys, Function keys,Printable ASCII characters, UTF-8 text input only

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
- fix focus goes to last window if taskar activewindowlist is removed
- snake
- fix window focus and priority events
- update startmenu
- update layouts to work with textual v.6.5.0
- fix vstack, hstack distribute dimensions evenly
- feat: wm: tiling swap windows, focus windows upgrade, code cleanup
- change: log to lib/display/console.py instead of textual console
- change: custom layouts & their children are now neighbor-aware
- add: new alternative ~full-featured~ xterminal
- add: initial readme
- change: executable smart focus tries to focus widget container first
- change: terminal.py to dustty.py

CONTINUE:
taskbar
VFS

TODO PRIORITY
- taskbar
- vfs
- workspace
- user system
- context menu
- settings
- trick alt terminal to use the vfs

TOFIX
dustty markdown
might refactor wm to use move_child as well for z-axis ordering

TODO UI
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

Polish:
tiled compact mode - no borders for windows; executables fill the windows; add separators (one line tall/wide) for neighboring windows
"""
from __future__ import annotations

from typing import Dict, Set, Tuple, cast

import lib.display.glyphs as glyphs
from bin.debug import Debug, DebugContent
from bin.dustty import Dustty
from bin.notepad import Notepad
from lib.core.events import ActiveWindowsChanged, Run
from lib.core.widgets import UIToast
from lib.debug2 import DomInfoOverlay
from lib.display.bar import ActiveWindowList, Taskbar
from lib.display.console import redirect_stdout
from lib.display.flyout import Flyout
from lib.display.window import Window
from lib.display.wm import Desktop
from lib.vfs import VFS, AppInfo
from textual import log, on, pilot, timer
from textual._border import BORDER_CHARS, BORDER_LOCATIONS
from textual.app import App, ComposeResult, Timer
from textual.containers import Container
from textual.css.constants import VALID_BORDER
from textual.events import MouseDown, MouseMove
from textual.geometry import Offset, Region
from textual.reactive import reactive
from textual.widgets import Label

# ─────────────────────────────────────────────────────────────────────────────
#  Textual Patch
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
#  Main Application
# ─────────────────────────────────────────────────────────────────────────────
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
        ("alt+shift+j", "move_window_direction('down')", "Move Down"),
        ("alt+shift+k", "move_window_direction('up')", "Move Up"),
        ("alt+h", "focus_direction('left')", "Focus Left"),
        ("alt+l", "focus_direction('right')", "Focus Right"),
        ("alt+shift+h", "move_window_direction('left')", "Move Left"),
        ("alt+shift+l", "move_window_direction('right')", "Move Right"),
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
        self.discovered_apps: dict[str, list[AppInfo]] | None = None

    def compose(self) -> ComposeResult:
        yield self.toast
        yield Desktop(id="desktop")
        yield Taskbar(id="taskbar")
        yield DomInfoOverlay(id="dom_info_overlay")

    def on_key(self, event):
        # for demo / debug
        self.show_keypress(f"{event.key}")
        # overrides default for precise control
        if event.key.startswith("alt+") and len(event.key) == 5:
            key = event.key[-1]
            if key.isalpha():
                was_handled = self.query_one(Taskbar).trigger_accelerator(key)
                if was_handled:
                    event.prevent_default()
                    event.stop()

    def on_mouse_down(self, event: MouseDown) -> None:
        """Called when the user clicks anywhere in the app."""
        try:
            flyouts = self.query(Flyout)
        except Exception as e:
            return
        if not flyouts:
            return
        for flyout in flyouts:
            if not flyout.region.contains(event.screen_x, event.screen_y):
                # If the click was outside, remove the popup.
                self.app.call_next(self.wm.close_active_flyout)

    def on_mount(self) -> None:
        self.discovered_apps = VFS.discover_apps("bin")
        self.wm = self.query_one(Desktop).wm
        redirect_stdout()  # console log

    def show_keypress(self, message: str, timeout: float = 1.5):
        def _center_toast():
            screen_width = self.size.width
            toast_width = self.toast.styles.width.value + len(message)
            new_offset_x = (screen_width - toast_width) // 2
            self.toast.styles.offset = (new_offset_x, 1)

        self.toast.show(message)
        _center_toast()

        if self.hide_toast_timer:
            self.hide_toast_timer.stop()

        self.hide_toast_timer = self.set_timer(timeout, self.toast.hide)

    @on(ActiveWindowsChanged)
    def update_taskbar(self, message: ActiveWindowsChanged):
        self.query_one(Taskbar).update_active_windows(message)

    @on(Run)
    async def on_run(self, message: Run) -> None:
        """Handles Run messages and spawn new application windows."""
        print(f"App received Run message for {message.executable.app_name}")
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
        print(f"Attempt: kill {window}.")
        target_window = self.wm.active_window if window is None else window
        if target_window:
            self.call_next(self.wm.close_window, target_window)
        else:
            print("sys_kill failed: No active window to kill.")

    async def action_cycle_window_mode(self) -> None:
        """Cycles through the available window layout modes."""
        print("App action: Cycling window mode.")
        self.wm.change_mode()

    def action_focus_direction(self, direction: str) -> None:
        """Moves focus in a specific direction in tiling modes."""
        print(f"App action: Focusing direction {direction}.")
        self.wm.focus_direction(direction)

    def action_move_window_direction(self, direction: str) -> None:
        print(f"App action: Moving direction {direction}.")
        self.wm.move_window_direction(direction)

    def action_focus_next_element(self) -> None:
        """Tells the WindowManager to focus the next element in the active window."""
        self.wm.cycle_focus_element(direction=1)

    def action_focus_previous_element(self) -> None:
        """Tells the WindowManager to focus the previous element in the active window."""
        self.wm.cycle_focus_element(direction=-1)

    async def action_cycle_focus(self, direction: str):
        print(f"App action: cycling focus {'next' if direction == 1 else 'previous'}.")
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
