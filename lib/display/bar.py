from datetime import datetime

import lib.display.glyphs as glyphs
from bin.debug import Debug
from bin.dustty import Dustty
# Import your app executables
from bin.notepad import Notepad
from lib.core.events import ActiveWindowsChanged, Run
from lib.core.widgets import UIButton
from lib.display.flyout import Flyout
from lib.display.window import Window
from lib.display.wm import Desktop, WMLayout
from lib.vfs import VFS, AppInfo
from textual import log, on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.events import Click, Key
from textual.geometry import Region
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widget import Widget
from textual.widgets import Button, OptionList, Select
from textual.widgets.option_list import Option


"""

START MENU TODO
+----------------------------+
| USR | Search: ...          |
+-------------+--------------+
| Category1<--| App1 [Desc]  |
| Category2   | App2 [Desc]  |
| Category3   | App3 [Desc]  |
+-------------+--------------+
| Sleep | Restart | Shutdown |
+----------------------------+
| Start |
+-------+

TASKBAR TODO
               _________
              |        |
              |        |
              |        |
+------------------------------+
| App1 | App2 | >App3< |       |
+------------------------------+
+--------+
|Pin     |
|Close   |
|App3 opt|
|App3 opt|
+--------+ Right click

+-------------+
| App3 [desc] |
+-------------+ Hover

Left Click > open | minimize | maximize
"""


class ActiveWindowList(Flyout):
    """A pop-up menu to display active windows."""
    def __init__(
        self,
        owner_id: str,
        app_id: str,
        windows: list[Window],
        active_window: Window | None,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.owner_id: str = owner_id
        self.app_id: str = app_id
        self.windows: list[Window] = windows
        self.active_window = active_window

    def compose(self) -> ComposeResult:
        """Compose the list of options."""
        options = []
        for i, window in enumerate(self.windows):
            options.append(Option(f"{window.executable.APP_NAME} #{i+1}", id=window.uuid))
        options.append(Option(f"New {self.app_id.capitalize()}", id=f"new_{self.app_id}"))
        yield OptionList(*options, id="active-windows-list")

    def on_key(self, event: Key):
        if event.key in ("escape"):
            self.app.call_next(self.wm.close_active_flyout)

    def on_mount(self) -> None:
        """Focus the list and highlight the active window."""
        self.wm = self.app.query_one("#desktop", Desktop).wm
        option_list = self.query_one(OptionList)
        if self.active_window:
            try:
                index = self.windows.index(self.active_window)
                option_list.highlighted = index
            except ValueError:
                pass
        option_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle a selection from the list."""
        # event.stop()
        option_id = event.option.id

        if option_id and option_id.startswith("new_"):
            if self.app_id == "notepad":
                self.app.post_message(Run(Notepad()))
            elif self.app_id == "terminal":
                self.app.post_message(Run(Dustty()))
            elif self.app_id == "debug":
                self.app.post_message(Run(Debug()))
        else:
            for window in self.windows:
                if window.uuid == option_id:
                    self.wm.set_active_window(window)
                    break
        self.app.call_next(self.wm.close_active_flyout)


class Taskbar(Horizontal):
    """The bottom taskbar with application launchers and widgets."""
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.active_windows: dict[str, list] = {}
        self._used_accelerators: set[str] = set()
        self._accelerator_map: dict[str, str] = {}

    def on_mount(self, event):
        self.wm = self.app.query_one("#desktop", Desktop).wm

    def compose(self) -> ComposeResult:
        with Horizontal(id="left-taskbar"):
            start_button = StartButton()
            start_button.label = self._create_accelerator_label(f"{glyphs.icons['start']} Start", "start-menu-button")
            yield start_button
        with Horizontal(id="center-taskbar"):
            yield UIButton(
                self._create_accelerator_label("Terminal", "btn-terminal"),
                id="btn-terminal", compact=True
            )
            yield UIButton(
                self._create_accelerator_label("Notepad", "btn-notepad"),
                id="btn-notepad", compact=True)
            yield UIButton(
                self._create_accelerator_label("Debug", "btn-debug"),
                id="btn-debug", compact=True
            )
        with Horizontal(id="right-taskbar"):
            yield WMLayout()
            yield Clock()

    def on_key(self, event):
        if event.key in ["left", "right", "enter"]:
            event.stop()

    def on_mouse_down(self, event):
        event.stop()

    def update_active_windows(self, message: ActiveWindowsChanged) -> None:
        """Updates the taskbar state and button appearance."""
        log(f"Taskbar received new window state: {message.active_windows}")
        # close existing activewindowlist
        awl = self.app.query(ActiveWindowList)
        for aw in awl:
            self.app.call_next(self.wm.close_active_flyout)
        self.active_windows = message.active_windows

        for button in self.query("UIButton"):
            app_id = button.id.replace("btn-", "")
            if app_id in self.active_windows:
                button.add_class("active")
            else:
                button.remove_class("active")

    def _create_accelerator_label(self, label: str, button_id: str) -> str:
        """
        Finds a unique accelerator key in a label
        """
        for i, char in enumerate(label):
            lower_char = char.lower()
            if lower_char.isalpha() and lower_char not in self._used_accelerators:
                self._used_accelerators.add(lower_char)
                self._accelerator_map[lower_char] = button_id
                return f"{label[:i]}[underline][$accent]{label[i]}[/][/]{label[i+1:]}"
        return label

    def trigger_accelerator(self, key: str) -> bool:
        """
        Finds a button associated with an accelerator key
        """
        button_id = self._accelerator_map.get(key.lower())
        if button_id:
            try:
                button = self.query_one(f"#{button_id}", UIButton)
                button.press()
                log("+++++++++++++++++++++++++++++++++")
                return True
            except Exception:
                log("---------------------------------")
                return False
        return False

    @on(Button.Pressed)
    def handle_button_press(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if not (button_id and button_id.startswith("btn-")):
            return

        app_id = button_id.replace("btn-", "")
        active_app_windows = self.active_windows.get(app_id)

        if active_app_windows:
            active_window = self.wm.active_window
            window_list_widget = ActiveWindowList(
                id=str(app_id),
                owner_id=button_id,
                app_id=app_id,
                windows=active_app_windows,
                active_window=active_window)

            button_region = event.button.region
            window_list_widget.styles.offset = (
                button_region.x,
                0
            )
            self.app.call_next(self.wm.request_flyout, window_list_widget)
        else:
            if app_id == "notepad":
                self.post_message(Run(Notepad()))
            elif app_id == "terminal":
                self.post_message(Run(Dustty()))
            elif app_id == "debug":
                self.post_message(Run(Debug()))


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
        icon = glyphs.icons["clock"]
        text = f" {icon} {self.time} "
        self.styles.width = len(text)
        return text


class PriorityOptionList(OptionList):
    """Catches on_click for itself"""
    def on_click(self, event: Click) -> None:
        event.prevent_default()
        event.stop()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """When an option is selected, pop the screen and post the message."""
        option_id = event.option.id

        if option_id:
            self.app.post_message(Run(option_id))

        self.app.pop_screen()

        event.stop()


class StartButton(UIButton):
    """A simple button that pushes the StartMenuScreen when clicked."""
    def __init__(self):
        super().__init__(f" Start", id="start-menu-button")

    def on_mount(self):
        self.wm = self.app.query_one("#desktop", Desktop).wm

    @on(Button.Pressed, '#start-menu-button')
    def on_button_press(self) -> None:
        start_menu = StartMenu(self.app.discovered_apps, id="start-menu")
        # button_region = self.region
        # # start_menu.styles.offset = (
        # #     button_region.x,
        # #     button_region.y
        # # )
        self.app.call_next(self.wm.request_flyout, start_menu)

    def on_mouse_down(self, event):
        event.stop()


class StartMenu(Flyout):
    """A floating start menu that shows applications."""

    DEFAULT_CSS = """
    """

    def __init__(self, discovered_apps: dict[str, list[AppInfo]], **kwargs) -> None:
        super().__init__(**kwargs)
        self.discovered_apps = discovered_apps
        self.categories = sorted(self.discovered_apps.keys())

    def compose(self) -> ComposeResult:
        """Compose the menu with just the OptionList."""
        yield OptionList(id="start-menu-list")

    def on_mount(self) -> None:
        self.wm = self.app.query_one("#desktop", Desktop).wm
        self._show_main_menu()
        option_list = self.query_one(OptionList)
        option_list.highlighted = 0
        option_list.focus()

    def _show_main_menu(self) -> None:
        option_list = self.query_one(OptionList)
        option_list.clear_options()
        for category in self.categories:
            option_list.add_option(
                Option(f" {glyphs.icons['folder']} {category}", id=f"category_{category}")
            )

        option_list.add_option(None)
        option_list.add_option(Option(f"{glyphs.icons['settings']} Settings", id="action_settings"))
        option_list.add_option(Option(f"{glyphs.icons['power']} Shutodwn", id="action_shutdown"))

    def _show_app_category(self, category_name: str) -> None:
        option_list = self.query_one(OptionList)
        option_list.clear_options()
        option_list.add_option(Option(" .. Back", id="show_main_menu"))
        option_list.add_option(None)
        for app in self.discovered_apps[category_name]:
            icon_char: str
            if app['icon_override'] is not None:
                icon_char = app['icon_override']
            elif app['icon_name']:
                icon_char = glyphs.icons.get(app['icon_name'], '?')
            else:
                icon_char = "?"
            option_list.add_option(
                Option(f"{icon_char} {app['name']}", id=f"app_{app['id']}")
            )
        option_list.highlighted = 0

    def on_key(self, event: Key) -> None:
        """Also dismiss on escape key."""
        if event.key in ("escape"):
            self.app.call_next(self.wm.close_active_flyout)

    @on(OptionList.OptionSelected)
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = str(event.option.id)
        if option_id.startswith("category_"):
            category = option_id.split("_", 1)[1]
            self._show_app_category(category)
        elif option_id.startswith("app_"):
            app_id = option_id.split("_", 1)[1]
            for category_apps in self.discovered_apps.values():
                for app in category_apps:
                    if app['id'] == app_id:
                        self.app.post_message(Run(app['cls']()))
                        self.app.call_next(self.wm.close_active_flyout)
                        return
        elif option_id == "show_main_menu":
            self._show_main_menu()
        elif option_id == "action_shutdown":
            self.app.call_next(self.wm.close_active_flyout)
            self.app.exit("Shutodwn requsted by user.")
