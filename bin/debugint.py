from lib.display.window import Executable
from textual.app import ComposeResult
from textual.containers import Container
from textual.widget import Widget
from textual.widgets import Footer, Static


class DebugInternals(Container):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.content_label = Static("")

    def compose(self) -> ComposeResult:
        yield self.content_label

    def on_mount(self) -> None:
        self.wm = self.app.query_one("#desktop", Container).wm
        self.set_interval(1, self.update_info)

    # A public method to let the main app feed it information.
    def update_info(self) -> None:
        window_container = str(self.wm.window_container)
        windows = str(self.wm.windows)
        active_window = str(self.wm.active_window)
        text = window_container + "\n" + windows + "\n" + active_window
        self.content_label.update(text)


class DBGINT(Executable):
    """This is the blueprint definition. It links metadata to the content widget."""
    APP_NAME = "DebugINT"
    APP_ID = "debugint"
    APP_ICON_OVERRIDE = " ● "
    APP_CATEGORY = "Development"
    MAIN_WIDGET = DebugInternals
