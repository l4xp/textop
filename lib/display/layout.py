from __future__ import annotations

import operator
from fractions import Fraction
from typing import TYPE_CHECKING, Literal, Optional

from textual import layout
from textual._resolve import resolve_box_models
from textual.geometry import NULL_OFFSET, Offset, Region, Size, Spacing
from textual.layout import ArrangeResult, Layout, WidgetPlacement
from textual.widget import Widget

if TYPE_CHECKING:
    from textual.widget import Widget

__all__ = ["CascadeLayout", "BSPLayout",
           "BSPAltLayout", "UltrawideLayout", "UltratallLayout",
           "HorizontalStackLayout", "VerticalStackLayout"]

"""
conceptual layouts
Card-cascade layout
The cascade layout mode is persistent. The CascadeLayout manager is always active.
When a user focuses a window (e.g., via alt+tab or by clicking its title bar):
The WindowManager's set_active_window method is triggered.
Instead of just adding a class, it would:
a. Take the newly focused window.
b. Promote it to a higher layer (e.g., layer: active or layer: top).
c. Give it a new, centered position on that layer (offset: 10% 10%).
d. When another window is focused, this one would be moved back down to the windows layer and lose its special offset, snapping back into its place in the cascade.

Traditional-cascade layout
Windows spawn in an organized stack.
Users can then drag them around freely.
A "tidy" command can instantly restore the perfect cascade arrangement.
"""


class CascadeLayout(Layout):
    """
    A custom layout that arranges widgets in a cascading stack.
    Each subsequent widget is offset by a fixed amount from the previous one
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

        resolve_margin = Size(0, 0)

        child_styles = [child.styles for child in children]
        box_models = resolve_box_models(
            [styles.width for styles in child_styles],
            children,
            size,
            viewport,
            resolve_margin,
            resolve_dimension="width",
        )

        x = 0
        y = 0

        for order, (widget, box_model) in enumerate(zip(children, box_models)):
            content_width, content_height, margin = box_model
            styles = widget.styles

            overlay = styles.overlay == "screen"
            absolute = styles.position == "absolute"

            region = Region(
                x=x + margin.left,
                y=y + margin.top,
                width=int(content_width),
                height=int(content_height),
            )

            offset = styles.offset.resolve(region.size, viewport)

            add_placement(
                WidgetPlacement(
                    region,
                    offset,
                    margin,
                    widget,
                    order,
                    False,
                    overlay,
                    absolute,
                )
            )

            if not overlay and not absolute:
                x += self.horizontal_offset
                y += self.vertical_offset

        return placements


class Node:
    """A node in our BSP tree. It can be a leaf (with a widget) or
    an internal node (with two children)."""
    def __init__(
        self,
        widget: Optional[Widget] = None,
        parent: Optional[Node] = None,
    ):
        self.widget = widget
        self.parent = parent
        self.children: list[Node] = []
        self.region = Region()
        self.split_direction: Literal["horizontal", "vertical"] = "vertical"

    def __repr__(self) -> str:
        return f"Node(widget={self.widget.id if self.widget else 'None'})"


class BSPLayout(Layout):
    """Binary Space Partitioning Layout (like tiling window managers)."""

    name = "bsp"

    def arrange(self, parent: Widget, children: list[Widget], size: Size, greedy: bool = True):
        parent.pre_layout(self)
        placements = []
        width, height = size

        if not children:
            return placements

        # Start with a single region covering the whole parent
        regions = [Region(0, 0, width, height)]

        # Generate regions using BSP logic
        for i in range(1, len(children)):
            last = regions.pop()
            if i % 2 == 1:
                # Odd index: split vertically (left and right)
                new_width = last.width // 2
                regions.append(Region(last.x, last.y, new_width, last.height))
                regions.append(Region(last.x + new_width, last.y, last.width - new_width, last.height))
            else:
                # Even index: split horizontally (top and bottom on the *right* region)
                new_height = last.height // 2
                regions.append(Region(last.x, last.y, last.width, new_height))
                regions.append(Region(last.x, last.y + new_height, last.width, last.height - new_height))

        # Assign regions to widgets
        for widget, region in zip(children, regions):
            placements.append(
                WidgetPlacement(
                    region=region,
                    offset=Offset(0, 0),
                    margin=Spacing(0, 0, 0, 0),
                    widget=widget,
                    order=0,
                    fixed=False,
                    overlay=False,
                    absolute=False,
                )
            )

        return placements


class BSPAltLayout(Layout):
    """
    +-----------------+
    |                 |
    |        1        |
    |                 |
    +--------+--------+
    |        |   3    |
    |    2   +--------+
    |        |   4    |
    +--------+--------+
    """
    """BSP layout that splits height first, then width."""
    name = "bsp_alt"

    def arrange(self, parent, children, size: Size, greedy: bool = True):
        parent.pre_layout(self)

        placements = []
        width, height = size

        if not children:
            return placements

        # Start with one full region
        regions = [Region(0, 0, width, height)]

        # True = split horizontally, False = split vertically
        split_horizontal = True

        for i in range(1, len(children)):
            last = regions.pop()

            if split_horizontal:
                # Split height into top + bottom
                h_half = last.height // 2
                regions.append(Region(last.x, last.y, last.width, h_half))
                regions.append(
                    Region(last.x, last.y + h_half, last.width, last.height - h_half)
                )
            else:
                # Split width into left + right
                w_half = last.width // 2
                regions.append(Region(last.x, last.y, w_half, last.height))
                regions.append(
                    Region(last.x + w_half, last.y, last.width - w_half, last.height)
                )

            split_horizontal = not split_horizontal

        # Assign widgets to calculated regions in order
        for widget, region in zip(children, regions):
            placements.append(
                WidgetPlacement(
                    region=region,
                    offset=Offset(0, 0),
                    margin=Spacing(0, 0, 0, 0),
                    widget=widget,
                    order=0,
                    fixed=False,
                    overlay=False,
                    absolute=False,
                )
            )

        return placements


class UltrawideLayout(Layout):
    """
    Wide layout optimized for ultrawide screens.
    +-----+-----------+-----+
    |     |           |  3  |
    |  1  |     2     +-----+
    |     |           |  4  |
    +-----+-----------+-----+
    """

    name = "ultra_wide"

    def arrange(self, parent, children, size: Size, greedy: bool = True):
        parent.pre_layout(self)
        placements = []

        if not children:
            return placements

        width, height = size
        N = len(children)

        # Case 1: Single full-screen widget
        if N == 1:
            region = Region(0, 0, width, height)
            placements.append(self._place(children[0], region))
            return placements

        # Case 2: Two equal columns
        if N == 2:
            half = width // 2
            regions = [
                Region(0, 0, half, height),
                Region(half, 0, width - half, height),
            ]
            for widget, region in zip(children, regions):
                placements.append(self._place(widget, region))
            return placements

        # Case 3 or more:
        # Widget 1: left 25%
        w1 = width // 4
        placements.append(self._place(children[0], Region(0, 0, w1, height)))

        # Widget 2: middle 50%
        w2 = width // 2
        placements.append(self._place(children[1], Region(w1, 0, w2, height)))

        # Remaining widgets fill the rightmost 25% column
        w3 = width - (w1 + w2)
        remaining = N - 2

        # Height per widget in the right column
        h_per = height // remaining if remaining else height

        y = 0
        for widget in children[2:]:
            h = h_per if widget != children[-1] else height - y
            region = Region(w1 + w2, y, w3, h)
            placements.append(self._place(widget, region))
            y += h

        return placements

    def _place(self, widget, region: Region):
        """Helper to create a WidgetPlacement with no margin/offset."""
        return WidgetPlacement(
            region=region,
            offset=Offset(0, 0),
            margin=Spacing(0, 0, 0, 0),
            widget=widget,
            order=0,
            fixed=False,
            overlay=False,
            absolute=False,
        )


class UltratallLayout(Layout):
    """
    +---------------------+
    |          1          |
    +---------------------+
    |          2          |
    +----------+----------+
    |    3     |     4    |
    +----------+----------+
    """
    name = "ultra_tall"

    def arrange(self, parent, children, size: Size, greedy: bool = True):
        parent.pre_layout(self)
        placements = []
        N = len(children)

        if N == 0:
            return placements

        width, height = size

        # 1 child → fullscreen
        if N == 1:
            placements.append(self._place(children[0], Region(0, 0, width, height)))
            return placements

        # 2 children → split horizontally equally
        if N == 2:
            half = height // 2
            placements.append(self._place(children[0], Region(0, 0, width, half)))
            placements.append(self._place(children[1], Region(0, half, width, height - half)))
            return placements

        # First two: top halves
        h1 = height // 4         # 25% for child 1
        h2 = height // 2         # 50% for child 2
        placements.append(self._place(children[0], Region(0, 0, width, h1)))
        placements.append(self._place(children[1], Region(0, h1, width, h2)))

        # Remaining area for children 3..N
        remaining_height = height - (h1 + h2)
        remaining_children = children[2:]
        count_rem = len(remaining_children)

        if count_rem == 1:
            # Just one widget takes bottom entire space
            placements.append(self._place(remaining_children[0], Region(0, h1 + h2, width, remaining_height)))
            return placements

        # Otherwise, divide bottom area into equal-width columns
        col_width = width // count_rem
        x = 0
        for i, widget in enumerate(remaining_children):
            # Last takes remaining pixels
            w = col_width if i < count_rem - 1 else width - x
            region = Region(x, h1 + h2, w, remaining_height)
            placements.append(self._place(widget, region))
            x += w

        return placements

    def _place(self, widget, region: Region):
        return WidgetPlacement(
            region=region,
            offset=Offset(0, 0),
            margin=Spacing(0, 0, 0, 0),
            widget=widget,
            order=0,
            fixed=False,
            overlay=False,
            absolute=False,
        )

class HorizontalStackLayout(Layout):
    """Arrange children in equal-width columns (horizontal tiling)."""

    name = "hstack"

    def arrange(self, parent, children, size: Size, greedy: bool = True):
        parent.pre_layout(self)

        placements = []
        total = len(children)
        if total == 0:
            return placements

        width, height = size
        col_width = width // total

        for index, widget in enumerate(children):
            region = Region(
                index * col_width,
                0,
                col_width if index < total - 1 else width - index * col_width,
                height,
            )
            placements.append(
                WidgetPlacement(
                    region=region,
                    offset=Offset(0, 0),
                    margin=Spacing(0, 0, 0, 0),
                    widget=widget,
                )
            )
        return placements


class VerticalStackLayout(Layout):
    """Arrange children in equal-height rows (vertical tiling)."""

    name = "vstack"

    def arrange(self, parent, children, size: Size, greedy: bool = True):
        parent.pre_layout(self)

        placements = []
        total = len(children)
        if total == 0:
            return placements

        width, height = size
        row_height = height // total

        for index, widget in enumerate(children):
            region = Region(
                0,
                index * row_height,
                width,
                row_height if index < total - 1 else height - index * row_height,
            )
            placements.append(
                WidgetPlacement(
                    region=region,
                    offset=Offset(0, 0),
                    margin=Spacing(0, 0, 0, 0),
                    widget=widget,
                )
            )
        return placements
