from datetime import datetime
from uuid import uuid4

from textual import log, on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, Widget
from textual.events import Focus, MouseDown, MouseMove, MouseUp
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Static
from windows.terminal import Terminal

# --------------------------
# Apps
# --------------------------


class Notepad(Widget):
    """Simple Notepad widget"""

    title = "⏍ Notepad"

    def __init__(self):
        super().__init__(id=f"notepad-{uuid4().hex[:6]}")

    def compose(self):
        yield Static("", id="title")


# class Terminal(Vertical):
#     """Simple Terminal widget"""
#     def __init__(self):
#         super().__init__(id=f"terminal-{uuid4().hex[:6]}")

#     def compose(self):
#         self.border_title = "🖳 Terminal"
#         yield Static("", id="title")

# --------------------------
# Window System
# --------------------------


class BringToFront(Message):
    """Message to request bringing a window to front"""
    def __init__(self, sender: Widget):
        self.widget = sender
        super().__init__()


class CloseWindow(Message):
    """Message to request bringing a window to front"""
    def __init__(self, sender: Widget):
        self.widget = sender
        super().__init__()


class Window(Static):
    """A draggable window that wraps another widget"""
    HEADER_HEIGHT = 1
    dragging = reactive(False)
    can_focus = True

    def __init__(self, child: Widget, index: int, **kwargs):
        super().__init__(**kwargs)
        self.child = child
        self.index = index
        self.offset_x = index * 2
        self.offset_y = index
        self._mouse_offset_x = 0
        self._mouse_offset_y = 0
        self._initialized = False
        self.id = f"window-{uuid4().hex[:6]}"

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static(self.child.title, id="window-title"),
            Button("x", id="exit", classes="exit-btn", compact=True),
            id="window-header"
        )
        yield self.child

    async def on_mount(self) -> None:
        if not self._initialized:
            self.styles.offset = (self.offset_x, self.offset_y)
            self._initialized = True

    @on(Button.Pressed, "#exit")
    async def close(self, event: Button.Pressed):
        self.post_message(CloseWindow(self))
    async def on_mouse_down(self, event: MouseDown) -> None:
        if event.y > self.HEADER_HEIGHT:
            # Close start menu on window interaction
            if hasattr(self.app, "close_startmenu"):
                await self.app.close_startmenu()

            self.dragging = True
            self._mouse_offset_x = event.x
            self._mouse_offset_y = event.y

            # Bring window to front
            self.post_message(BringToFront(self))
            self.screen.set_focus(self.child)
            self.query_one('#window-header').add_class('focus')

            # Unfocus siblings
            for sibling in self.parent.children:
                if sibling is not self and isinstance(sibling, Window):
                    sibling.blur()
                    sibling.parent.query_one('#window-header').remove_class('focus')

    def on_mouse_up(self, event: MouseUp) -> None:
        # self.release_mouse()
        self.dragging = False

    def on_mouse_move(self, event: MouseMove) -> None:
        if self.dragging:
            dx = event.screen_x - self._mouse_offset_x
            dy = event.screen_y - self._mouse_offset_y
            self.styles.offset = (dx, dy)


# --------------------------
# UI Elements
# --------------------------

class Taskbar(Horizontal):
    """Bottom taskbar with buttons"""
    def compose(self) -> ComposeResult:
        yield Button("⌘ Start", id="start-button", compact=True)
        yield Button("🖳 Terminal", id="btn-terminal", compact=True)
        yield Button("⏍ Notepad", id="btn-notepad", compact=True)
        yield Clock()


class Startmenu(Vertical):
    """Popup Start menu"""
    def compose(self) -> ComposeResult:
        yield Button("⌘ Start", id="start-button", compact=True)
        yield Button("🖳 Terminal", id="btn-terminal", compact=True)
        yield Button("⏍ Notepad", id="btn-notepad", compact=True)


# --------------------------
# Taskbar Widgets
# --------------------------


class Clock(Widget):
    """Live digital clock widget"""
    time = reactive("")

    def on_mount(self):
        # Update every second
        self.timer = self.set_interval(1.0, self.update_time)
        self.update_time()

    def update_time(self):
        # Format: HH:MM:SS (24hr)
        self.time = datetime.now().strftime("%I:%M %p")

    def render(self) -> str:
        return '⏲ ' + self.time


# --------------------------
# Main App
# --------------------------


class Termos(App):
    CSS_PATH = "styles.tcss"

    active_windows: int = 0
    menu_open: bool = False
    last_clicked_button: str | None = None

    def compose(self) -> ComposeResult:
        yield Container(id="desktop")
        yield Taskbar(id="taskbar")

    # --- Start Menu Logic

    async def close_startmenu(self):
        """Close start menu if open"""
        if self.menu_open:
            try:
                menu = self.query_one('#startmenu')
                await menu.remove()
            except Exception:
                pass
            self.menu_open = False

    # --- Window Manager
    def is_front(self, widget: Widget) -> bool:
        desktop = self.query_one("#desktop")
        return desktop.children[-1] == widget

    async def on_bring_to_front(self, message: BringToFront):
        """Bring selected window to front without"""
        desktop = self.query_one("#desktop")
        widget = message.widget

        # Remove and re-mount at end (top of stacking order)
        # can't access internal ._nodes anymore (on textual 3.x)
        if not self.is_front(widget):
            self.set_focus(None)
            await widget.remove()
            await desktop.mount(widget)
            self.set_focus(widget.child)
    async def on_close_window(self, message: CloseWindow):
        desktop = self.query_one('#desktop')
        widget = message.widget

        await widget.remove()
    # --- Mouse & UI Input Handling

    async def on_mouse_down(self, event: MouseDown) -> None:
        """Global mouse click handler"""
        if self.last_clicked_button == "start-button":
            self.last_clicked_button = None
            return

        try:
            menu = self.query_one('#startmenu')
            if not menu.region.contains(event.x, event.y):
                await self.close_startmenu()
        except Exception:
            pass

        self.last_clicked_button = None

    async def on_button_pressed(self, event: Button.Pressed):
        """Handle all button presses"""
        self.last_clicked_button = event.button.id

        # Auto-close start menu for all except start-button
        if self.menu_open and event.button.id != "start-button":
            await self.close_startmenu()

        desktop = self.query_one("#desktop")
        idx = self.active_windows

        match event.button.id:
            case "start-button":
                if self.menu_open:
                    await self.close_startmenu()
                else:
                    await desktop.mount(Startmenu(id="startmenu"))
                    self.menu_open = True

            case "btn-terminal":
                await self.spawn_window(desktop, Terminal(), idx)

            case "btn-notepad":
                await self.spawn_window(desktop, Notepad(), idx)

    async def spawn_window(self, desktop: Widget, app_widget: Widget, idx: int):
        """Create and focus a new window"""
        win = Window(app_widget, idx)
        await desktop.mount(win)

        self.set_focus(app_widget)
        self.active_windows += 1


if __name__ == "__main__":
    Termos().run()
