import random
from collections import namedtuple

from lib.display import glyphs
from lib.display.window import Executable
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.events import Key
from textual.geometry import Size
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Footer, Input, Label, Static

# divide the console into a grid of cells
# divide the grid into a normalized grid of (2 x 1) cells
# each normalized cell is 2 console grid wide, and 1 console grid tall
# to fix, re-handle food pos on resize


class Vector(namedtuple("Vector", ["x", "y"])):
    __slots__ = ()

    def __add__(self, other):
        return Vector(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        return Vector(self.x - other.x, self.y - other.y)

    def __mod__(self, other):
        return Vector(self.x % other.x, self.y % other.y)

    def __mul__(self, other):
        return Vector(self.x * other.x, self.y * other.y)

    def __div__(self, other):
        return Vector(self.x / other.x, self.y / other.y)

    def __neg__(self):
        return Vector(-self.x, -self.y)

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y

    def __hash__(self):
        return hash((self.x, self.y))


UP = Vector(0, -1)
DOWN = Vector(0, 1)
RIGHT = Vector(1, 0)
LEFT = Vector(-1, 0)


class ScoreChanged(Message):
    def __init__(self, score: int):
        super().__init__()
        self.score = score


class _Apple:
    def __init__(self):
        self.position: Vector | None = None

    def spawn(self, boundary: Vector, snake_body: list[Vector]):
        cells = [Vector(x, y) for y in range(boundary.y) for x in range(boundary.x)]
        empty_cells = list(set(cells) - set(snake_body))

        if self.position:
            empty_cells = [cell for cell in empty_cells if cell != self.position]

        if not empty_cells:
            self.position = None
            return
        self.position = random.choice(empty_cells)

    def consume(self):
        self.position = None

    def exists(self):
        return self.position is not None


class _Snake:
    def __init__(
        self,
        init_length: int = 5,
        init_position: Vector = Vector(0, 0),
        direction: Vector = RIGHT
    ):
        self.init_length = init_length
        self.init_position = init_position
        self.direction: Vector = direction
        self.body: list[Vector] | None = None
        self.has_moved: bool = True
        self.length: int = init_length
        self.is_growing: bool = False

    def get_body(self):
        if not self.body:
            # constuct
            body = []
            position = self.init_position
            for i in range(self.init_length):
                segment = position + self.direction
                body.append(segment)
                position += self.direction
            self.body = body
        return self.body

    def get_head(self):
        return self.body[-1]

    def move(self, boundary: Vector):
        if self.body:
            head = self.body[-1]
            tail = self.body[0]
            new_head = (head + self.direction) % boundary
            if new_head in self.body:
                return
            self.body.append(new_head)
            self.body.pop(0)
            if self.length > len(self.body):
                self.body.insert(0, tail)
            if self.is_growing:
                self.length += 1
                self.is_growing = False
            self.has_moved = True

    def turn(self, direction: Vector):
        if not self.has_moved:
            return
        self.has_moved = False
        if direction == -self.direction:
            return
        self.direction = direction

    def eat(self, apple: _Apple):
        apple.consume()
        self.grow()

    def grow(self):
        self.is_growing = True


class SnakeGame(Static):
    game_matrix = None
    score = 0
    can_focus = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._snake = _Snake()
        self._apple = _Apple()

    def on_mount(self):
        w = self.size.width
        if w % 2 != 0:
            w -= 1
        h = self.size.height
        self.game_matrix = [[None for _ in range(0, w, 2)] for _ in range(h)]
        self.set_interval(1 / 30, self._update)

    def on_resize(self, event):
        w = self.size.width
        if w % 2 != 0:
            w -= 1
        h = self.size.height
        self.game_matrix = [[None for _ in range(0, w, 2)] for _ in range(h)]
        self.refresh()

    def on_key(self, event):
        if event.key == "left":
            self._snake.turn(LEFT)
        elif event.key == "right":
            self._snake.turn(RIGHT)
        elif event.key == "up":
            self._snake.turn(UP)
        elif event.key == "down":
            self._snake.turn(DOWN)

    def render(self):
        snake = self._snake.get_body()
        text = str()
        char = "  "
        for y, row in enumerate(self.game_matrix):
            for x, col in enumerate(row):
                if Vector(x, y) in snake:
                    char = glyphs.icons.get("block", ":") * 2
                elif self._apple.exists() and Vector(x, y) == self._apple.position:
                    char = "[]"
                else:
                    char = "  "
                text += char
            text += "\n"
        return text

    def _update(self):
        snake_body = self._snake.get_body()

        if not self.game_matrix or not self.game_matrix[0]:
            return

        matrix_width = len(self.game_matrix[0])
        matrix_height = len(self.game_matrix)

        if not self._apple.exists():
            self._apple.spawn(Vector(matrix_width, matrix_height), snake_body)

        if self._apple.exists() and self._apple.position == self._snake.get_head():
            self._snake.eat(self._apple)
            self.score += 1
            self.post_message(ScoreChanged(self.score))

        boundary = Vector(matrix_width, matrix_height)
        self._snake.move(boundary)
        self.refresh()


class SnakeUI(Vertical):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.time = 0.0

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label("Score: ", id="score")
            yield Label("Time: ", id="time")
            yield Label("HighScore:", id="highscore")
        yield SnakeGame()

    def on_mount(self):
        self.set_interval(1.0, self.update_time)

    def update_time(self):
        self.query_one("#time", Label).update(f"Time: {self.time}")
        self.time += 1.0

    @on(ScoreChanged)
    def on_score_changed(self, event):
        self.query_one("#score", Label).update(f"Score: {event.score}")


class Snake(Executable):
    APP_NAME = "Snake"
    APP_ICON_OVERRIDE = "[S]"
    APP_ID = "snake"
    APP_CATEGORY = "Games"
    MAIN_WIDGET = SnakeUI
