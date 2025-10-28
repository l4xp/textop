from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widget import Widget
from textual.widgets import Button, Label


class UIButton(Button):
    ALLOW_MAXIMIZE = False


class UIToast(Widget):
    """A reusable temporary toast overlay that auto-hides after a timeout."""

    DEFAULT_CSS = """
    Toast {

    }
    """

    def __init__(self,  **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = Label()

    def compose(self) -> ComposeResult:
        yield self._label

    def hide(self) -> None:
        self.remove_class("visible")

    def show(self, message: str, timeout=None) -> None:
        self._label.update(message)
        self.add_class("visible")


class Flyout(Container):
    """A temporary popup interface"""
    def __init__(self):
        super().__init__()
