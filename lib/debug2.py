# lib/debug_screens.py
from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.rule import Rule
from textual import events, log
from textual.app import App
from textual.containers import Container
from textual.geometry import Region, Size
from textual.widget import Widget
from textual.widgets import Static


##############################################################################
# lib/debug2.py
class DOMInfoRenderable:
    """A renderable that shows a widget's DOM information."""
    def __init__(self, widget: Widget) -> None:
        self._widget = widget

    def __rich__(self) -> Group:
        # ... (implementation is the same as before)
        widget = self._widget
        return Group(
            Rule("[b blue]DOM Hierarchy[/]"),
            "\n".join(f"[dim]{node!r}[/]" for node in widget.ancestors_with_self),
            Rule("[b green]Dimensions[/]"),
            f"[bold]Container:[/][yellow] {widget.container_size}[/]",
            f"[bold]Content:[/][yellow] {widget.content_size}[/]",
            Rule("[b red]CSS[/]"),
            f"[dim]{widget.styles.css.strip()}[/]",
            Rule(),
        )
class DomInfoOverlay(Container):
    """
    An overlay that displays DOM info and can be paused for interaction.
    """
    DEFAULT_CSS = """
    DomInfoOverlay {
        position: absolute; /* Manual offset requires absolute positioning */
        background: $panel;
        border: thick $primary;
        color: $text;
        width: 50%;
        height: auto;
        max-height: 45%;
        layer: critical;
        display: none;
        overflow: auto;
        transition: border 150ms in_out_cubic;
    }
    DomInfoOverlay.paused {
        border: thick $secondary;
    }
    """
    # ... (__init__, compose, is_visible, toggle_visibility, pause are unchanged) ...

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._content_area = Static("")
        self._is_visible = False
        self._is_paused = False
        self._last_target_id: int | None = None

    def compose(self) -> ComposeResult:
        yield self._content_area

    @property
    def is_visible(self) -> bool:
        return self._is_visible

    def toggle_visibility(self) -> None:
        """Toggles whether the overlay is shown or hidden."""
        self._is_visible = not self._is_visible
        self.styles.display = "block" if self._is_visible else "none"
        if not self._is_visible:
            self.pause(False)
            self._last_target_id = None
        self.app.notify(f"DOM Inspector: {'ON' if self._is_visible else 'OFF'}", timeout=1.5)

    def pause(self, paused: bool) -> None:
        """Explicitly sets the paused state."""
        if not self.is_visible and paused: return
        self._is_paused = paused
        self.set_class(paused, "paused")
        self.app.notify(
            f"Inspector: {'PAUSED' if paused else 'Resumed'}",
            title="DOM Inspector",
            timeout=1.5
        )

    def update_and_position(self, mouse_x: int, mouse_y: int, target_widget: Widget) -> None:
        """Main update method, guarded by the paused state."""
        if not self.is_visible or self._is_paused:
            return

        current_target_id = id(target_widget)
        if current_target_id != self._last_target_id:
            self._last_target_id = current_target_id
            self._content_area.update(DOMInfoRenderable(target_widget))

        self.call_after_refresh(self._reposition, mouse_x, mouse_y)

    def _reposition(self, mouse_x: int, mouse_y: int) -> None:
        """Calculates and sets the corner offset after a refresh."""
        screen_width, screen_height = self.app.size
        center_x, center_y = screen_width / 2, screen_height / 2
        overlay_width, overlay_height = self.size
        margin = 1

        # Calculate final X position
        final_x = (screen_width - overlay_width - margin) if mouse_x < center_x else margin
        # Calculate final Y position
        final_y = (screen_height - overlay_height - margin) if mouse_y < center_y else margin

        self.styles.offset = (final_x, final_y)
