import lib.display.glyphs as glyphs
from lib.display.window import Executable
from lib.vfs import classproperty
from textual.widget import Widget
from textual.widgets import TextArea


class Note(Widget):
    def compose(self):
        yield TextArea(id="app-content")


class Notepad(Executable):
    """A simple text editor application."""
    APP_NAME = "Notepad"
    APP_ID = "notepad"
    APP_ICON_NAME = "notepad"
    APP_CATEGORY = "Accessories"
    MAIN_WIDGET = Note

    DEFAULT_CSS = """
    #app-content {
        border: none;
        width: 100%;
        height: 100%;
    }
    """
