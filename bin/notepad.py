import lib.display.glyphs as glyphs
from lib.display.window import Executable
from textual.widgets import TextArea


class Notepad(Executable):
    """A simple text editor application."""
    APP_NAME = "Notepad"
    APP_ID = "notepad"
    MAIN_WIDGET = TextArea

    DEFAULT_CSS = """
    #app-content {
        hatch: horizontal $panel;
        border: none;
        width: 100%;
        height: 100%;
    }
    """

    @property
    def APP_ICON(self): return glyphs.icons.get("notepad", "?")
