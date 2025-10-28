import lib.display.glyphs as glyphs
from lib.display.window import Executable
from lib.vfs import classproperty
from textual.widgets import TextArea


class Notepad(Executable):
    """A simple text editor application."""
    APP_NAME = "Notepad"
    APP_ID = "notepad"
    APP_ICON_NAME = "notepad"
    APP_CATEGORY = "Accessories"
    MAIN_WIDGET = TextArea

    DEFAULT_CSS = """
    #app-content {
        hatch: horizontal $panel;
        border: none;
        width: 100%;
        height: 100%;
    }
    """
