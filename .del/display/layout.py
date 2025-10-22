from __future__ import annotations

from typing import TYPE_CHECKING

# --- Paste the CascadeLayout class from above here ---
from textual._resolve import resolve_box_models
from textual.geometry import Region, Size, Spacing
from textual.layout import ArrangeResult, Layout, WidgetPlacement

if TYPE_CHECKING:
    from .textual.widget import Widget


class CascadeLayout(Layout):
    """
    A custom layout that arranges widgets in a cascading stack.
    Each subsequent widget is offset by a fixed amount from the previous one,
    creating an overlapping effect.
    """

    name = "cascade"

    def __init__(self, horizontal_offset: int = 2, vertical_offset: int = 1):
        """Initializes a CascadeLayout.

        Args:
            horizontal_offset: The number of cells to offset each subsequent widget to the right.
            vertical_offset: The number of cells to offset each subsequent widget downwards.
        """
        self.horizontal_offset = horizontal_offset
        self.vertical_offset = vertical_offset
        super().__init__()

    def arrange(
        self, parent: Widget, children: list[Widget], size: Size
    ) -> ArrangeResult:
        """Arrange widgets in a cascade.

        Args:
            parent: The parent widget.
            children: The child widgets to arrange.
            size: The available size.

        Returns:
            An ArrangeResult.
        """
        parent.pre_layout(self)
        placements: list[WidgetPlacement] = []
        add_placement = placements.append
        viewport = parent.app.size

        resolve_margin=Size(0, 0)
        # For a cascade layout, we don't need complex margin collapsing logic
        # between widgets, as they are intentionally overlapped. We simply
        # resolve the box model for each child individually.
        child_styles = [child.styles for child in children]
        box_models = resolve_box_models(
            [styles.width for styles in child_styles],
            children,
            size,
            viewport,
            resolve_margin,  # No inter-widget margins to resolve
            resolve_dimension="width",  # Resolve width fractions first
        )

        # These will be our running coordinates for the top-left of each widget.
        x = 0
        y = 0

        # We use enumerate to get a simple Z-index (order).
        # Widgets added later in the list will have a higher order, appearing on top.
        for order, (widget, box_model) in enumerate(zip(children, box_models)):
            content_width, content_height, margin = box_model
            styles = widget.styles

            # Widgets with overlay or absolute positioning are handled specially.
            # They do not participate in the layout flow.
            overlay = styles.overlay == "screen"
            absolute = styles.position == "absolute"

            # The region for the widget is placed at the current (x, y)
            # plus its own top/left margin.
            region = Region(
                x=x + margin.left,
                y=y + margin.top,
                width=int(content_width),
                height=int(content_height),
            )

            # Let the widget handle its own `offset` style if present.
            # This is separate from the layout's positioning.
            offset = styles.offset.resolve(region.size, viewport)

            add_placement(
                WidgetPlacement(
                    region,
                    offset,
                    margin,
                    widget,
                    order, # Use the loop index for Z-ordering
                    False,
                    overlay,
                    absolute,
                )
            )

            # If the widget is part of the layout flow, advance the coordinates
            # for the next widget in the cascade.
            if not overlay and not absolute:
                x += self.horizontal_offset
                y += self.vertical_offset

        return placements
