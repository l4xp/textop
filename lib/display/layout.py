from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Literal, Optional

from textual._resolve import resolve_box_models
from textual.geometry import Region, Size, Spacing
from textual.layout import ArrangeResult, Layout, WidgetPlacement

if TYPE_CHECKING:
    from textual.widget import Widget

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


class BSPLargestLayout(Layout):
    """
    +-----+-----+-----+-----+
    |     |  2  |     |  4  |
    |  1  +-----+  3  +-----+
    |     |  5  |     |  6  |
    +-----+-----+-----+-----+
    """

    name = "bsp"

    def arrange(
        self, parent: Widget, children: list[Widget], size: Size
    ) -> ArrangeResult:
        """Arrange widgets using a BSP algorithm.

        Args:
            parent: The parent widget.
            children: The child widgets to arrange.
            size: The available size.

        Returns:
            An ArrangeResult.
        """
        parent.pre_layout(self)

        flow_children = [
            child
            for child in children
            if child.styles.overlay != "screen" and child.styles.position != "absolute"
        ]
        if not flow_children:
            return []

        # This dictionary will map each flow widget to its final region
        child_regions: dict[Widget, Region] = {}

        # The first widget gets the whole space
        child_regions[flow_children[0]] = Region(0, 0, size.width, size.height)

        # Iteratively split space for the rest of the widgets
        for i in range(1, len(flow_children)):
            new_widget = flow_children[i]

            # Find the largest region among the already-placed widgets
            # We use the region's area (width * height) as the key for finding the max
            widget_to_split, region_to_split = max(
                child_regions.items(), key=lambda item: item[1].area
            )

            # Decide whether to split vertically or horizontally
            if region_to_split.width > region_to_split.height:
                # Split vertically
                split_width = region_to_split.width // 2
                x, y, width, height = region_to_split

                # The original widget gets the left half
                child_regions[widget_to_split] = Region(
                    x, y, split_width, height
                )
                # The new widget gets the right half
                child_regions[new_widget] = Region(
                    x + split_width, y, width - split_width, height
                )
            else:
                # Split horizontally
                split_height = region_to_split.height // 2
                x, y, width, height = region_to_split

                # The original widget gets the top half
                child_regions[widget_to_split] = Region(
                    x, y, width, split_height
                )
                # The new widget gets the bottom half
                child_regions[new_widget] = Region(
                    x, y + split_height, width, height - split_height
                )

        # --- Generate final placements for ALL children ---
        placements: list[WidgetPlacement] = []
        viewport = parent.app.size

        for order, widget in enumerate(children):
            styles = widget.styles

            # Get the region from our calculated map if it's a flow widget
            # Otherwise, it's an overlay/absolute widget and doesn't get a BSP region
            full_region = child_regions.get(widget)

            if full_region is None:
                # This handles overlay, absolute, or non-flow children
                # They don't take up space in the layout
                region = Region(0, 0, 0, 0)
                margin = Spacing()
            else:
                # For flow children, shrink the allocated region by the widget's margin
                margin = styles.margin
                region = full_region.shrink(margin)

            offset = styles.offset.resolve(region.size, viewport)

            placements.append(
                WidgetPlacement(
                    region=region,
                    offset=offset,
                    margin=margin,
                    widget=widget,
                    order=order,
                    fixed=False,
                    overlay=styles.overlay == "screen",
                    absolute=styles.position == "absolute",
                )
            )

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


class BSPSpiralLayout(Layout):
    """
    +-----+-----+-----+-----+
    |           |     2     |
    |     1     +-----+-----+
    |           |  3  |  4  |
    +-----+-----+-----+-----+
    """
    name = "bsp_spiral"

    def arrange(
        self, parent: Widget, children: list[Widget], size: Size
    ) -> ArrangeResult:
        parent.pre_layout(self)

        flow_children = [
            c for c in children
            if c.styles.overlay != "screen" and c.styles.position != "absolute"
        ]

        if not flow_children:
            return []

        root = self._build_tree(flow_children)
        self._arrange_nodes(root, Region(0, 0, size.width, size.height))

        # Get ALL leaf nodes from the tree
        leaf_nodes = self._get_leaf_nodes(root)
        node_map: dict[Widget, Node] = {
            node.widget: node for node in leaf_nodes if node.widget
        }

        placements: list[WidgetPlacement] = []
        for order, widget in enumerate(children):
            node = node_map.get(widget)
            styles = widget.styles
            if node:
                margin = styles.margin
                region = node.region.shrink(margin)
            else:
                region = Region(0, 0, 0, 0)
                margin = Spacing()

            offset = styles.offset.resolve(region.size, parent.app.size)
            placements.append(
                WidgetPlacement(
                    region, offset, margin, widget, order, False,
                    styles.overlay == "screen", styles.position == "absolute"
                )
            )
        return placements

    def _build_tree(self, flow_children: list[Widget]) -> Node:
        """Constructs the BSP tree based on the order of children."""
        if not flow_children:
            return Node()

        root = Node(widget=flow_children[0])
        last_node = root

        for widget_to_add in flow_children[1:]:
            node_to_split = last_node
            new_internal_node = Node(parent=node_to_split.parent)

            if node_to_split.parent:
                parent_direction = node_to_split.parent.split_direction
                new_internal_node.split_direction = (
                    "horizontal" if parent_direction == "vertical" else "vertical"
                )
            else:
                new_internal_node.split_direction = "vertical"

            node_to_split.parent = new_internal_node
            new_widget_node = Node(widget=widget_to_add, parent=new_internal_node)
            new_internal_node.children = [node_to_split, new_widget_node]

            if new_internal_node.parent:
                for i, child in enumerate(new_internal_node.parent.children):
                    if child is node_to_split:
                        new_internal_node.parent.children[i] = new_internal_node
                        break
            else:
                root = new_internal_node

            last_node = new_widget_node

        return root

    def _arrange_nodes(self, node: Node, region: Region):
        """Recursively calculates the region for each node in the tree. (Unchanged)"""
        node.region = region
        if node.children:
            child1, child2 = node.children
            if node.split_direction == "vertical":
                r1, r2 = region.split_vertical(region.width // 2)
            else: # horizontal
                r1, r2 = region.split_horizontal(region.height // 2)
            self._arrange_nodes(child1, r1)
            self._arrange_nodes(child2, r2)

    def _get_leaf_nodes(self, node: Node) -> list[Node]:
        """Performs a traversal to find all leaf nodes (those with widgets)."""
        if not node.children:
            return [node] if node.widget else []

        leaves: list[Node] = []
        for child in node.children:
            leaves.extend(self._get_leaf_nodes(child))
        return leaves


class UltrawideLayout(Layout):
    """
    +-----+-----+-----+-----+
    |     |           |  4  |
    |  1  |     2     +-----+
    |     |           |  5  |
    +-----+-----+-----+-----+
    """
    name = "ultrawide"

    def __init__(self, master_pane_fraction: float = 0.5):
        self.master_pane_fraction = master_pane_fraction
        super().__init__()

    def arrange(
        self, parent: Widget, children: list[Widget], size: Size
    ) -> ArrangeResult:
        parent.pre_layout(self)

        flow_children = [
            c for c in children
            if c.styles.overlay != "screen" and c.styles.position != "absolute"
        ]

        widget_regions: dict[Widget, Region] = {}
        count = len(flow_children)

        if count == 0:
            pass
        elif count == 1:
            widget_regions[flow_children[0]] = Region(0, 0, size.width, size.height)
        elif count == 2:
            widget1, widget2 = flow_children
            region1, region2 = Region(0, 0, size.width, size.height).split_vertical(size.width // 2)
            widget_regions[widget1] = region1
            widget_regions[widget2] = region2
        else:  # count >= 3
            master_width = int(size.width * self.master_pane_fraction)
            side_width = (size.width - master_width) // 2

            left_column_region = Region(0, 0, side_width, size.height)
            master_region = Region(side_width, 0, master_width, size.height)
            right_column_x = side_width + master_width
            right_column_width = size.width - right_column_x
            right_column_region = Region(right_column_x, 0, right_column_width, size.height)

            widget_regions[flow_children[0]] = left_column_region
            widget_regions[flow_children[1]] = master_region

            right_stack_widgets = flow_children[2:]
            stack_count = len(right_stack_widgets)

            if stack_count > 0:
                remaining_region = right_column_region
                remaining_widgets_count = stack_count

                for widget_in_stack in right_stack_widgets[:-1]:
                    # Calculate the size for this widget's pane
                    pane_height = remaining_region.height // remaining_widgets_count

                    # Split the remaining region to create a pane for this widget
                    pane, remaining_region = remaining_region.split_horizontal(pane_height)

                    widget_regions[widget_in_stack] = pane
                    remaining_widgets_count -= 1

                # The very last widget gets whatever space is left
                widget_regions[right_stack_widgets[-1]] = remaining_region

        placements: list[WidgetPlacement] = []
        for order, widget in enumerate(children):
            styles = widget.styles
            full_region = widget_regions.get(widget)

            if full_region is None:
                region = Region(0, 0, 0, 0)
                margin = Spacing()
            else:
                margin = styles.margin
                region = full_region.shrink(margin)

            offset = styles.offset.resolve(region.size, parent.app.size)
            placements.append(
                WidgetPlacement(
                    region, offset, margin, widget, order, False,
                    styles.overlay == "screen", styles.position == "absolute"
                )
            )
        return placements
