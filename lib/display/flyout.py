from textual.containers import Container


class Flyout(Container):
    """A temporary popup interface"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
