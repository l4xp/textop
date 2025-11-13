from __future__ import annotations

import operator
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING, Literal, Optional

from textual import layout
from textual._resolve import resolve_box_models
from textual.geometry import NULL_OFFSET, Offset, Region, Size, Spacing
from textual.layout import ArrangeResult, Layout, WidgetPlacement
from textual.widget import Widget

if TYPE_CHECKING:
    from textual.widget import Widget

__all__ = ["BSPLayout",
           "BSPAltLayout", "UltrawideLayout", "UltratallLayout",
           "HorizontalStackLayout", "VerticalStackLayout"]


@dataclass
class _Node:
    # Internal node representing a subtree of the BSP.
    # If leaf: widget is set and left/right are None and region is the leaf region.
    region: Region
    widget: Optional[Widget] = None
    split: Optional[str] = None  # 'vertical' or 'horizontal' for internal nodes
    left: Optional["_Node"] = None
    right: Optional["_Node"] = None
    parent: Optional["_Node"] = None

    def is_leaf(self) -> bool:
        return self.widget is not None and self.left is None and self.right is None


class BSPLayout(Layout):
    """
    Binary Space Partitioning layout (width-first variant).
    Diagram:
    +--------+-----------+
    |        |     2     |  ← first vertical split
    |    1   +-----+-----+
    |        |  3  |  4  |  ← second horizontal split (inside right subtree)
    +--------+-----+-----+
    (left/right split first, then alternate with up/down)

    Neighbors:
    1: 2-right
    2: 1-left, 3-down
    3: 1-left, 2-up, 4-right
    4: 2-up, 3-left

    Rules:
    - Right: if current split is vertical, move into the right subtree’s first visible child
             or climb upward to the parent’s right sibling if applicable.
    - Left: if current split is vertical, move into the left subtree’s last visible child
            or climb upward to the parent’s left sibling if applicable.
    - Down: if the current node is part of a horizontal split, move into the lower sibling subtree.
    - Up: if the current node is part of a horizontal split, move into the upper sibling subtree;
           otherwise, climb upward to the parent’s upper neighbor if available.
    """
    name = "bsp"

    def __init__(self):
        super().__init__()
        # widget -> leaf node
        self._leaf_for_widget: Dict[Widget, _Node] = {}
        # cached neighbor map built from the tree (optional but cheap)
        self._neighbors: Dict[Tuple[Widget, str], Widget] = {}

    def get_neighbor(self, widget: Widget, direction: str) -> Optional[Widget]:
        return self._neighbors.get((widget, direction))

    def arrange(self, parent: Widget, children: List[Widget], size: Size, greedy: bool = True):
        parent.pre_layout(self)
        self._leaf_for_widget.clear()
        self._neighbors.clear()
        placements: List[WidgetPlacement] = []
        width, height = size

        if not children:
            return placements

        # Build tree by iterative splitting of the last leaf (same insertion rule as your previous code).
        root = _Node(region=Region(0, 0, width, height))
        leaves: List[_Node] = [root]

        for i in range(1, len(children)):
            # pop last leaf and split it
            leaf = leaves.pop()
            if i % 2 == 1:
                # vertical split -> left / right
                half = leaf.region.width // 2
                left_region = Region(leaf.region.x, leaf.region.y, half, leaf.region.height)
                right_region = Region(leaf.region.x + half, leaf.region.y, leaf.region.width - half, leaf.region.height)
                left_node = _Node(region=left_region, parent=leaf)
                right_node = _Node(region=right_region, parent=leaf)
                leaf.split = "vertical"
                leaf.left = left_node
                leaf.right = right_node
                # append children in left-to-right order (keeps leaf list consistent)
                leaves.append(left_node)
                leaves.append(right_node)
            else:
                # horizontal split -> top / bottom
                half = leaf.region.height // 2
                top_region = Region(leaf.region.x, leaf.region.y, leaf.region.width, half)
                bottom_region = Region(leaf.region.x, leaf.region.y + half, leaf.region.width, leaf.region.height - half)
                top_node = _Node(region=top_region, parent=leaf)
                bottom_node = _Node(region=bottom_region, parent=leaf)
                leaf.split = "horizontal"
                leaf.left = top_node   # left==top for horizontal split
                leaf.right = bottom_node
                leaves.append(top_node)
                leaves.append(bottom_node)

        # Now leaves list is the leaf nodes in insertion order; assign widgets to them
        # If there are more leaves than widgets (shouldn't be), we only assign as many as children.
        for widget, leaf in zip(children, leaves):
            leaf.widget = widget
            self._leaf_for_widget[widget] = leaf
            placements.append(
                WidgetPlacement(
                    region=leaf.region,
                    offset=Offset(0, 0),
                    margin=Spacing(0, 0, 0, 0),
                    widget=widget,
                    order=0,
                    fixed=False,
                    overlay=False,
                    absolute=False,
                )
            )

        # Build neighbor map using classic BSP tree neighbor algorithm:
        # climb until you find a parent where sibling is on the requested side,
        # then descend sibling to the appropriate extreme leaf.
        def descend_extreme(node: _Node, direction: str) -> Optional[_Node]:
            """Given an internal node subtree where we want the 'closest' leaf in that subtree
            for a particular direction, walk down selecting child that is nearer the direction.
            For right -> choose leftmost descendant; left -> choose rightmost descendant;
            up -> choose bottommost descendant (since 'up' wants the nearest at the top of that subtree),
            down -> choose topmost descendant (choose topmost?? We'll choose the opposite to get nearest).
            We'll implement explicitly per direction.
            """
            cur = node
            while not cur.is_leaf():
                if cur.split == "vertical":
                    # vertical split: left x < right x
                    if direction == "right":
                        # to get closest on the right, we should go to the leftmost leaf of the right subtree
                        cur = cur.leftmost_in_subtree()  # we will implement helpers below
                    elif direction == "left":
                        cur = cur.rightmost_in_subtree()
                    else:
                        # for up/down, choose child that is vertically closer (choose both by overlap later)
                        # fallback: pick child with topmost/bottommost depending on direction
                        cur = cur.left  # arbitrary fallback (we'll not usually reach here)
                else:  # horizontal split
                    # left==top, right==bottom
                    if direction == "down":
                        # descendant closest downward should be the topmost leaf of bottom subtree
                        cur = cur.leftmost_in_subtree_in_direction("down")  # we'll use simpler helpers below
                    elif direction == "up":
                        cur = cur.leftmost_in_subtree_in_direction("up")
                    else:
                        cur = cur.left
            return cur

        # Instead of embedding complex helper logic inside that function (which is awkward),
        # define small helpers on the fly for descending extremes:

        def leftmost(node: _Node) -> _Node:
            cur = node
            while not cur.is_leaf():
                # always go to left child to reach leftmost leaf
                cur = cur.left
            return cur

        def rightmost(node: _Node) -> _Node:
            cur = node
            while not cur.is_leaf():
                cur = cur.right
            return cur

        def topmost(node: _Node) -> _Node:
            # "topmost" for our horizontal splits corresponds to repeatedly choosing left child
            cur = node
            while not cur.is_leaf():
                # for horizontal split, left==top; for vertical split, topmost is ambiguous -- choose the child with smaller y
                if cur.split == "horizontal":
                    cur = cur.left
                else:
                    # if vertical split, pick the child whose region.y is smaller
                    # compute which child has smaller y
                    if cur.left.region.y <= cur.right.region.y:
                        cur = cur.left
                    else:
                        cur = cur.right
            return cur

        def bottommost(node: _Node) -> _Node:
            cur = node
            while not cur.is_leaf():
                if cur.split == "horizontal":
                    cur = cur.right
                else:
                    if cur.left.region.y + cur.left.region.height >= cur.right.region.y + cur.right.region.height:
                        cur = cur.left
                    else:
                        cur = cur.right
            return cur

        # Provide these as bound methods on _Node via closures for clarity:
        _Node.leftmost_in_subtree = leftmost
        _Node.rightmost_in_subtree = rightmost
        _Node.topmost_in_subtree = topmost
        _Node.bottommost_in_subtree = bottommost

        # climb/neighbor algorithm
        def find_neighbor_by_tree(leaf: _Node, direction: str) -> Optional[_Node]:
            cur = leaf
            parent = cur.parent
            while parent is not None:
                # for vertical split, left child is left/top depending on split semantics above
                if parent.split == "vertical":
                    # left = left side, right = right side
                    if direction == "right" and parent.left is cur:
                        # sibling subtree is parent.right; neighbor is leftmost leaf of that subtree
                        return leftmost(parent.right)
                    if direction == "left" and parent.right is cur:
                        return rightmost(parent.left)
                elif parent.split == "horizontal":
                    # left == top, right == bottom
                    if direction == "down" and parent.left is cur:
                        # sibling subtree is bottom (parent.right); choose topmost leaf there
                        return topmost(parent.right)
                    if direction == "up" and parent.right is cur:
                        return bottommost(parent.left)
                cur = parent
                parent = cur.parent
            return None

        # Build neighbor map per widget
        for widget, leaf in self._leaf_for_widget.items():
            for direction in ("left", "right", "up", "down"):
                neighbor_node = find_neighbor_by_tree(leaf, direction)
                if neighbor_node is not None:
                    self._neighbors[(widget, direction)] = neighbor_node.widget

        return placements


class BSPAltLayout(Layout):
    """
    Binary Space Partitioning layout (height-first variant).
    Diagram:
    +-----------------+
    |        1        |  ← top (first horizontal split)
    +--------+--------+
    |   2    |   3    |  ← second vertical split (inside bottom half)
    |        |--------+
    |        |   4    |  ← third horizontal split on right subtree
    +--------+--------+

    Neighbors:
    1: 2-down
    2: 1-up, 3-right
    3: 1-up, 2-left, 4-down
    4: 3-up

    Rules:
    - Right: move into the right subtree’s first visible child (on the same split level).
    - Left: move to the parent’s opposite sibling
    - Down: if the current node is part of a horizontal split, move into the lower sibling subtree.
    - Up: if the current node is part of a horizontal split, move into the upper sibling subtree.
           otherwise, climb upward to the parent’s upper neighbor if available.

    This layout mirrors BSP but rotated 90°
    the first split is horizontal (height-based), and subsequent splits alternate in axis.
    """
    name = "bsp_alt"

    def __init__(self):
        super().__init__()
        self._leaf_for_widget: Dict[Widget, _Node] = {}
        self._neighbors: Dict[Tuple[Widget, str], Widget] = {}

    def get_neighbor(self, widget: Widget, direction: str) -> Optional[Widget]:
        """Return the visual neighbor of a widget in a given direction."""
        return self._neighbors.get((widget, direction))

    def arrange(self, parent: Widget, children: List[Widget], size: Size, greedy: bool = True):
        parent.pre_layout(self)
        self._leaf_for_widget.clear()
        self._neighbors.clear()
        placements: List[WidgetPlacement] = []
        width, height = size

        if not children:
            return placements

        # --- Build BSP Tree ---
        root = _Node(region=Region(0, 0, width, height))
        leaves: List[_Node] = [root]
        split_horizontal = True  # Start with height (y-axis) split first

        for i in range(1, len(children)):
            leaf = leaves.pop()
            if split_horizontal:
                # Split top/bottom
                half = leaf.region.height // 2
                top = Region(leaf.region.x, leaf.region.y, leaf.region.width, half)
                bottom = Region(
                    leaf.region.x,
                    leaf.region.y + half,
                    leaf.region.width,
                    leaf.region.height - half,
                )
                leaf.split = "horizontal"
                leaf.left = _Node(region=top, parent=leaf)
                leaf.right = _Node(region=bottom, parent=leaf)
                leaves.extend([leaf.left, leaf.right])
            else:
                # Split left/right
                half = leaf.region.width // 2
                left = Region(leaf.region.x, leaf.region.y, half, leaf.region.height)
                right = Region(
                    leaf.region.x + half,
                    leaf.region.y,
                    leaf.region.width - half,
                    leaf.region.height,
                )
                leaf.split = "vertical"
                leaf.left = _Node(region=left, parent=leaf)
                leaf.right = _Node(region=right, parent=leaf)
                leaves.extend([leaf.left, leaf.right])

            split_horizontal = not split_horizontal

        # --- Assign widgets to leaves ---
        for widget, leaf in zip(children, leaves):
            leaf.widget = widget
            self._leaf_for_widget[widget] = leaf
            placements.append(
                WidgetPlacement(
                    region=leaf.region,
                    offset=Offset(0, 0),
                    margin=Spacing(0, 0, 0, 0),
                    widget=widget,
                    order=0,
                    fixed=False,
                    overlay=False,
                    absolute=False,
                )
            )

        # --- Recursive neighbor finding (swapping axes) ---
        def find_neighbor_by_tree(leaf: _Node, direction: str) -> Optional[_Node]:
            cur = leaf
            parent = cur.parent
            while parent is not None:
                if parent.split == "horizontal":  # Top/Bottom split (acts like left/right in BSP)
                    if direction == "down" and parent.left is cur:
                        return _leftmost_leaf(parent.right)
                    if direction == "up" and parent.right is cur:
                        return _rightmost_leaf(parent.left)
                elif parent.split == "vertical":  # Left/Right split (acts like up/down in BSP)
                    if direction == "right" and parent.left is cur:
                        return _leftmost_leaf(parent.right)
                    if direction == "left" and parent.right is cur:
                        return _rightmost_leaf(parent.left)
                cur = parent
                parent = cur.parent
            return None

        # --- Helper functions to pick visual edges ---
        def _leftmost_leaf(node: _Node) -> _Node:
            while not node.is_leaf():
                node = node.left
            return node

        def _rightmost_leaf(node: _Node) -> _Node:
            while not node.is_leaf():
                node = node.right
            return node

        # --- Build neighbor map ---
        for widget, leaf in self._leaf_for_widget.items():
            for direction in ("left", "right", "up", "down"):
                neighbor = find_neighbor_by_tree(leaf, direction)
                if neighbor is not None:
                    self._neighbors[(widget, direction)] = neighbor.widget

        return placements


class UltrawideLayout(Layout):
    """
    Wide layout optimized for wide screens.
    +-----+-----------+-----+
    |     |           |  3  |
    |  1  |     2     +-----+
    |     |           |  4  |
    +-----+-----------+-----+
    neighbors:
    1: 2-right
    2: 1-left, 3-right
    ---
    3: 2-left, 4-down
    4: 2-left, 3-up
    n: 2-left, n-1-up, n+1-down
    """
    name = "ultra_wide"

    def __init__(self):
        super().__init__()
        self._neighbors: dict[tuple[Widget, str], Widget] = {}

    def get_neighbor(self, widget: Widget, direction: str) -> Widget | None:
        return self._neighbors.get((widget, direction))

    def arrange(self, parent, children, size: Size, greedy: bool = True):
        parent.pre_layout(self)
        placements = []
        self._neighbors.clear()

        if not children:
            return placements

        width, height = size
        N = len(children)

        if N == 1:
            region = Region(0, 0, width, height)
            placements.append(self._place(children[0], region))
            return placements

        if N == 2:
            half = width // 2
            regions = [
                Region(0, 0, half, height),
                Region(half, 0, width - half, height),
            ]
            for widget, region in zip(children, regions):
                placements.append(self._place(widget, region))
            # Neighbor map for 1 and 2
            self._neighbors[(children[0], "right")] = children[1]
            self._neighbors[(children[1], "left")] = children[0]
            return placements

        # Widget 1: left 25%
        w1 = width // 4
        placements.append(self._place(children[0], Region(0, 0, w1, height)))
        # Widget 2: middle 50%
        w2 = width // 2
        placements.append(self._place(children[1], Region(w1, 0, w2, height)))
        # Remaining widgets fill the rightmost 25%
        w3 = width - (w1 + w2)
        remaining = N - 2
        h_per = height // remaining if remaining else height

        y = 0
        for widget in children[2:]:
            h = h_per if widget != children[-1] else height - y
            region = Region(w1 + w2, y, w3, h)
            placements.append(self._place(widget, region))
            y += h

        # --- Build neighbor map ---
        # Widget 1 → right = 2
        self._neighbors[(children[0], "right")] = children[1]
        # Widget 2 → left = 1, right = first of right column
        self._neighbors[(children[1], "left")] = children[0]
        self._neighbors[(children[1], "right")] = children[2]

        # Widgets in right column: vertical stack, left = 2
        for i, widget in enumerate(children[2:]):
            if i > 0:
                # up/down links
                self._neighbors[(widget, "up")] = children[2 + i - 1]
            if i < len(children[2:]) - 1:
                self._neighbors[(widget, "down")] = children[2 + i + 1]
            self._neighbors[(widget, "left")] = children[1]

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


class UltratallLayout(Layout):
    """
    Tall layout optimized for terminals.
    +---------------------+
    |          1          |
    +---------------------+
    |          2          |
    +----------+----------+
    |    3     |     4    |
    +----------+----------+
    neighbors:
    1: 2-down
    2: 1-up, 3-down
    ---
    3: 2-up, 4-right
    4: 2-up, 3-left
    n: 2-up, n-1-left, n+1-right
    """
    name = "ultra_tall"

    def __init__(self):
        super().__init__()
        self._neighbors: dict[tuple[Widget, str], Widget] = {}

    def get_neighbor(self, widget: Widget, direction: str) -> Widget | None:
        return self._neighbors.get((widget, direction))

    def arrange(self, parent, children, size: Size, greedy: bool = True):
        parent.pre_layout(self)
        placements = []
        self._neighbors.clear()

        N = len(children)
        if N == 0:
            return placements

        width, height = size

        # --- Fullscreen ---
        if N == 1:
            placements.append(self._place(children[0], Region(0, 0, width, height)))
            return placements

        # --- Two widgets → top halves ---
        if N == 2:
            half = height // 2
            placements.append(self._place(children[0], Region(0, 0, width, half)))
            placements.append(self._place(children[1], Region(0, half, width, height - half)))
            # Neighbors
            self._neighbors[(children[0], "down")] = children[1]
            self._neighbors[(children[1], "up")] = children[0]
            return placements

        # --- First two widgets ---
        h1 = height // 4
        h2 = height // 2
        placements.append(self._place(children[0], Region(0, 0, width, h1)))
        placements.append(self._place(children[1], Region(0, h1, width, h2)))

        # Vertical neighbors
        self._neighbors[(children[0], "down")] = children[1]
        self._neighbors[(children[1], "up")] = children[0]

        # --- Bottom row: widgets 3+ ---
        remaining_children = children[2:]
        count_rem = len(remaining_children)
        remaining_height = height - (h1 + h2)
        col_width = width // count_rem
        x = 0
        for i, widget in enumerate(remaining_children):
            # Last widget takes remaining width
            w = col_width if i < count_rem - 1 else width - x
            region = Region(x, h1 + h2, w, remaining_height)
            placements.append(self._place(widget, region))
            x += w

        # --- Neighbor map for bottom row ---
        for i, widget in enumerate(remaining_children):
            if i > 0:
                self._neighbors[(widget, "left")] = remaining_children[i - 1]
            if i < count_rem - 1:
                self._neighbors[(widget, "right")] = remaining_children[i + 1]
            # Up always points to widget 2
            self._neighbors[(widget, "up")] = children[1]

        # Connect middle (2) to bottom row’s first widget
        first_bottom = remaining_children[0]
        self._neighbors[(children[1], "down")] = first_bottom
        self._neighbors[(first_bottom, "up")] = children[1]

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
    """
    Stacking layout, splits height
    +---------------------+
    |          1          |
    +---------------------+
    |          2          |
    +----------+----------+
    |          3          |
    +----------+----------+
    neighbors:
    1: 2-down
    2: 1-up, 3-down
    3: 2-up
    n: n-1-up, n+1-down
    """
    name = "hstack"

    def __init__(self):
        super().__init__()
        self._neighbors: dict[tuple[Widget, str], Widget] = {}

    def arrange(self, parent, children, size: Size, greedy=True):
        placements = []
        width, height = size
        total = len(children)
        if total == 0:
            return placements

        col_width = width // total
        x = 0
        self._neighbors.clear()
        for i, widget in enumerate(children):
            w = col_width if i < total - 1 else width - x
            region = Region(x, 0, w, height)
            placements.append(
                WidgetPlacement(region, Offset(0, 0), Spacing(0, 0, 0, 0), widget)
            )
            # neighbors
            if i > 0:
                self._neighbors[(widget, "left")] = children[i-1]
            if i < total - 1:
                self._neighbors[(widget, "right")] = children[i+1]
            x += w

        return placements

    def get_neighbor(self, widget, direction: str):
        return self._neighbors.get((widget, direction))


class VerticalStackLayout(Layout):
    """
    Stacking layout, splits width
    +-----------------+
    |     |     |     |
    |     |     |     |
    |  1  |  2  |  3  |
    |     |     |     |
    |     |     |     |
    +-----------------+
    neighbors:
    1: 2-right
    2: 1-left, 3-right
    3: 2-left
    n: n-1-left, n+1-right
    """
    name = "vstack"

    def __init__(self):
        super().__init__()
        self._neighbors: dict[tuple[Widget, str], Widget] = {}

    def arrange(self, parent, children, size: Size, greedy=True):
        placements = []
        width, height = size
        total = len(children)
        if total == 0:
            return placements

        col_height = height // total
        y = 0
        self._neighbors.clear()
        for i, widget in enumerate(children):
            h = col_height if i < total - 1 else height - y
            region = Region(0, y, width, h)
            placements.append(
                WidgetPlacement(region, Offset(0, 0), Spacing(0, 0, 0, 0), widget)
            )
            # neighbors
            if i > 0:
                self._neighbors[(widget, "up")] = children[i-1]
            if i < total - 1:
                self._neighbors[(widget, "down")] = children[i+1]
            y += h

        return placements

    def get_neighbor(self, widget, direction: str):
        return self._neighbors.get((widget, direction))
