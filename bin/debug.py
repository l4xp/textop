from lib.display.window import Executable
from textual.app import ComposeResult
from textual.containers import Container
from textual.widget import Widget
from textual.widgets import Footer, Static


class DebugContent(Container):
    """
    The actual content and logic for the Debug app.
    This is a self-contained component.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.content_label = Static("")

    def compose(self) -> ComposeResult:
        yield self.content_label
        yield Footer()

    def on_mount(self) -> None:
        self.content_label.update("Move the mouse to see debug information.")

    # A public method to let the main app feed it information.
    def update_info(self, text: str) -> None:
        self.content_label.update(text)


class Debug(Executable):
    """This is the blueprint definition. It links metadata to the content widget."""
    APP_NAME = "Debug"
    APP_ID = "debug"
    APP_ICON_OVERRIDE = " ● "
    APP_CATEGORY = "Development"
    MAIN_WIDGET = DebugContent
