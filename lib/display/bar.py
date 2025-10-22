from datetime import datetime

import lib.display.glyphs as glyphs
from bin.debug import Debug
from bin.notepad import Notepad
from bin.terminal import Dustty
from lib.core.events import Run
from lib.core.widgets import UIButton
from lib.display.wm import WMLayout
from textual import log, on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.events import Click, Key
from textual.message import Message
from textual.reactive import reactive
from textual.screen import Screen
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

# Define a custom message to run an application
class RunApp(Message):
    def __init__(self, app_id: str):
        self.app_id = app_id
        super().__init__()


class Taskbar(Horizontal):
    """The bottom taskbar with application launchers and widgets."""
    def compose(self) -> ComposeResult:
        with Horizontal(id="left-taskbar"):
            yield StartButton()
        with Horizontal(id="center-taskbar"):
            yield UIButton(f"{glyphs.icons["terminal"]}Terminal", id="btn-terminal", compact=True)
            yield UIButton(f"{glyphs.icons["notepad"]}Notepad", id="btn-notepad", compact=True)
            yield UIButton(f" {glyphs.taskbar["debug"]}Debug", id="btn-debug", compact=True)
        with Horizontal(id="right-taskbar"):
            yield WMLayout()
            yield Clock()

    @on(Button.Pressed, "#btn-notepad")
    def open_notepad(self):
        self.post_message(Run(Notepad()))

    @on(Button.Pressed, "#btn-terminal")
    def open_terminal(self):
        self.post_message(Run(Dustty()))

    @on(Button.Pressed, "#btn-debug")
    def open_debug(self):
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
        icon = glyphs.taskbar["clock"]
        text = f" {icon} {self.time} "
        self.styles.width = len(text)
        return text


class StartButton(UIButton):
    """A simple button that pushes the StartMenuScreen when clicked."""
    def __init__(self):
        super().__init__(f"{glyphs.taskbar["start"]} Start", id="start-menu-button")

    @on(Button.Pressed, '#start-menu-button')
    def on_button_press(self) -> None:
        self.app.push_screen(StartMenuScreen())


class PriorityOptionList(OptionList):
    """Catches on_click for itself"""
    def on_click(self, event: Click) -> None:
        event.prevent_default()
        event.stop()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """When an option is selected, pop the screen and post the message."""
        option_id = event.option.id

        if option_id:
            self.app.post_message(RunApp(option_id))

        self.app.pop_screen()

        event.stop()


class StartMenuScreen(Screen):
    """A modal screen that appears as the start menu."""

    # This screen will have a transparent background to see the app behind it.
    DEFAULT_CSS = """
    """

    def compose(self) -> ComposeResult:
        """Compose the menu with just the OptionList."""
        menu_items = [
            None,
            Option(f"{glyphs.icons["terminal"]}Terminal", id="terminal"),
            Option(f"{glyphs.icons["notepad"]}Notepad", id="notepad"),
            Option(f"{glyphs.taskbar["debug"]}Debug", id="debug"),
            None,
            Option(f"{glyphs.icons["settings"]}Settings", id="settings"),
            Option(f"{glyphs.taskbar["power"]}Shutdown", id="shutdown"),
            None,
        ]

        yield PriorityOptionList(*menu_items, id="start-menu-options")

    # Still enabled if clicked anywhere on the screen
    def on_click(self, event: Click) -> None:
        self.app.pop_screen()
        event.stop()

    def on_mount(self) -> None:
        """Focus the OptionList when the screen is mounted."""
        self.query_one(PriorityOptionList).focus()

    def on_key(self, event: Key) -> None:
        """Also dismiss on escape key."""
        if event.key == "escape":
            self.app.pop_screen()
            event.stop()


# alternative
class StartMenu0(Select):
    """A custom Start Menu widget built using Textual's Select."""

    def __init__(self, **kwargs):
        self.menu_options = [
            ("──────────────────", "divider"),
            (f"{glyphs.icons["terminal"]}Terminal", "terminal"),
            (f"{glyphs.icons["notepad"]}Notepad", "notepad"),
            (f"{glyphs.taskbar["debug"]}Debug", "debug"),
            ("──────────────────", "divider"),
            (f"{glyphs.icons["settings"]}Settings", "settings"),
            (f"{glyphs.taskbar["power"]}Shutdown", "shutdown"),
            ("──────────────────", "divider"),
        ]

        super().__init__(
            options=self.menu_options,
            prompt=" ⌘ Start",
            allow_blank=True,
            compact=True,
            **kwargs
        )

    def on_mount(self):
        # longest selection text
        self.styles.width = max([len(a[0]) for a in self.menu_options])
        log(max([len(a) for a in self.menu_options]))

    def on_select_changed(self, event: Select.Changed) -> None:
        """Called when the user selects an item from the dropdown."""
        selected_value = event.value

        self.app.notify(f"Selected: {selected_value}")

        if selected_value and selected_value != "divider":
            if selected_value == "shutdown":
                self.app.exit("Shutdown requested by user.")
            else:
                pass
        self.call_next(self.clear)
