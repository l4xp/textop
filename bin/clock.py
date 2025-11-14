"""Clock app using digits from textual docs. Minimal change"""
from datetime import datetime

from lib.display.window import Executable
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Digits


class ClockApp(Widget):
    def compose(self) -> ComposeResult:
        yield Digits("", id="clock")

    def on_mount(self) -> None:
        self.update_clock()
        self.set_interval(1, self.update_clock)

    def update_clock(self) -> None:
        clock = datetime.now().time()
        self.query_one(Digits).update(f"{clock:%T}")


class Clock(Executable):
    """A simple clock display."""
    APP_NAME = "Clock"
    APP_ID = "clock"
    APP_ICON_NAME = "clock"
    APP_CATEGORY = "System Tools"
    MAIN_WIDGET = ClockApp

    DEFAULT_CSS = """
    ClockApp {
        align: center middle;
    }
    ClockApp > Digits {
        width: auto;
    }
    #app-content {
        border: none;
        width: 100%;
        height: 100%;
    }
    """
