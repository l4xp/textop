import shlex
from typing import Optional, Tuple

import lib.display.glyphs as glyphs
from lib.display.window import Executable
from lib.vfs import VFS  # Assuming your VFS class is in this file
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.events import Key
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Label, Static


class PromptWidget(Horizontal):
    """A single, reusable command prompt widget containing a label and an input."""

    def compose(self) -> ComposeResult:
        yield Label("guest:", id="prompt-user")
        yield Label("", id="prompt-path") # The path is dynamic
        yield Label("$", id="prompt-symbol")
        yield Input(value="", id="prompt-input", valid_empty=True)

    def on_mount(self) -> None:
        self.focus_input()

    def focus_input(self) -> None:
        self.query_one("#prompt-input", Input).focus()


class VFSTerminalWidget(Widget):
    """
    A sandboxed terminal widget built on a persistent prompt architecture,
    providing a robust, scrollable, and feature-rich command line interface.
    """
    DEFAULT_CSS = """
    /* Main container for the terminal's scrollable content */
    VerticalScroll {
        width: 100%;
        height: 100%;
    }
    /* Container for the read-only history blocks */
    #history-container {
        height: auto;
    }
    #prompt-label {
        height: 1;
    }
    #prompt-input, #prompt-input:focus {
        background: transparent;
        border: none;
        padding: 0;
        width: 1fr;
    }
    #prompt-user {
        color: $text-success;
        text-style: bold;
    }
    #prompt-path {
        color: $text-primary;
    }
    #prompt-symbol {
        color: $accent;
        text-style: bold;
        padding-right: 1;
    }
    .output {
        /* Default style for command output */
        color: $text;
    }
    .error {
        /* Style for error messages */
        color: $error;
        text-style: bold;
    }
    .welcome {
        /* Style for the welcome message */
        color: $success;
        text-style: bold;
    }
    .prompt-history{
        height: 1;
    }
    .prompt-history > Static {
        width: auto;
    }
    """

    def __init__(self, vfs_root: str = "./home", **kwargs):
        super().__init__(**kwargs)
        # --- Core Components ---
        self.vfs = VFS(vfs_root)

        # --- Command History State ---
        self._command_history: list[str] = []
        self._history_cursor: int = 0
        self._draft_input: str = ""

        # --- Widget References ---
        self.scroll_view: VerticalScroll = VerticalScroll()
        self.history_container: Container = Container()
        self.current_prompt: PromptWidget = PromptWidget()

        # --- The Command Dispatcher ---
        self.commands = {
            "ls": self._cmd_ls, "cd": self._cmd_cd, "cat": self._cmd_cat,
            "help": self._cmd_help, "clear": self._cmd_clear, "touch": self._cmd_touch,
            "mkdir": self._cmd_mkdir, "rm": self._cmd_rm, "pwd": self._cmd_pwd,
        }

    def compose(self) -> ComposeResult:
        """Lays out the terminal with a scrollable history and a persistent prompt."""
        with VerticalScroll() as vs:
            yield Container(id="history-container")
            yield PromptWidget(id="current-prompt")

    def on_mount(self) -> None:
        """Get stable references to our layout components and display welcome message."""
        self.scroll_view = self.query_one(VerticalScroll)
        self.history_container = self.query_one("#history-container", Container)
        self.current_prompt = self.query_one("#current-prompt", PromptWidget)

        self._update_prompt_label()
        welcome_message = "Welcome to the Dustty Terminal!\nType 'help' for available commands."
        self.history_container.mount(Static(welcome_message, classes="welcome"))

    def _update_prompt_label(self) -> None:
        """Updates the path portion of the prompt label."""
        path_label = self.current_prompt.query_one("#prompt-path", Label)
        path_label.update(self.vfs.cwd)

    # --- Event Handlers for Snap-to-Bottom Behavior ---
    def on_key(self, event: Key) -> None:
        """
        Handles key presses when the input is NOT focused.
        This is for the "click away, scroll, then type" scenario.
        """
        input_widget = self.current_prompt.query_one("#prompt-input", Input)
        if event.is_printable and not input_widget.has_focus:
            self.scroll_to_bottom()
            input_widget.focus()
            input_widget.post_message(event)
            event.stop()

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """
        Handles the case where the input IS focused but the user has scrolled away.
        Typing changes the input, which triggers this event and snaps the view down.
        """
        self.scroll_to_bottom()

    # --- REPL ---
    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handles command submission atomically to prevent visual flicker."""
        input_widget = event.input
        command_str = event.value

        user_label = self.current_prompt.query_one("#prompt-user", Label)
        path_label = self.current_prompt.query_one("#prompt-path", Label)
        symbol_label = self.current_prompt.query_one("#prompt-symbol", Label)

        static_user = Static(user_label.renderable, id="prompt-user")
        static_path = Static(path_label.renderable, id="prompt-path")
        static_symbol = Static(symbol_label.renderable, id="prompt-symbol")
        static_command = Static(command_str, classes="prompt-command")

        frozen_prompt_container = Horizontal(
            static_user, static_path, static_symbol, static_command,
            classes="prompt-history"
        )

        widgets_to_add = [frozen_prompt_container]

        if command_str.strip():
            result = self._execute_command(command_str.strip())
            if result:
                content, style_class = result
                widgets_to_add.append(Static(content, classes=style_class, markup=False))

        with self.app.batch_update():
            self.history_container.mount(*widgets_to_add)
            input_widget.clear()
            self._update_prompt_label()

        self.scroll_to_bottom()

    def _execute_command(self, command_str: str) -> Optional[Tuple[str, str]]:
        """
        Parses and executes a command.

        Returns:
            A tuple of (content, css_class) on success or error.
            None if the command produces no output (e.g., cd).
        """
        try:
            parts = shlex.split(command_str)
            command_name = parts[0]
            args = parts[1:]

            if command_name in self.commands:
                return self.commands[command_name](args)
            else:
                return (f"Command not found: {command_name}", "error")
        except Exception as e:
            return (str(e), "error")

    def scroll_to_bottom(self, animate: bool = False):
        """Scroll to the bottom if possible."""
        if self.scroll_view is not None:
            self.scroll_view.call_after_refresh(lambda: self.scroll_view.scroll_end(animate=animate))

    # --- Command Implementations ---

    def _cmd_ls(self, args: list[str]) -> Tuple[str, str]:
        """ls [PATH]

        List directory contents. If PATH is not specified, lists
        the contents of the current directory.
        """
        path = args[0] if args else "."
        content = "\n".join(self.vfs.ls(path))
        return (content, "output") # Return content and the 'output' class

    def _cmd_cd(self, args: list[str]) -> None:
        """cd <DIRECTORY>

        Change the current working directory to DIRECTORY.
        """
        if not args:
            raise ValueError("Usage: cd <directory>") # Raise errors, let execute_command handle them
        self.vfs.cd(args[0])
        return None # This command has no output

    def _cmd_cat(self, args: list[str]) -> Tuple[str, str]:
        """cat <FILE>

        Display the contents of a file.
        """
        if not args:
            raise ValueError("Usage: cat <file>")
        content = self.vfs.cat(args[0])
        return (content, "output")

    def _cmd_help(self, args: list[str]) -> Tuple[str, str]:
        """help [COMMAND]

        Display helpful information about built-in commands.
        If COMMAND is specified, gives detailed help on that command.
        """
        if not args:
            header = (
                "Sandboxed Shell, v1.0\n"
                "Type `help [bold]\\[command][/]` for more info.\n"
            )
            summaries = [f"  {name:<15} {func.__doc__.strip().splitlines()[0]}" for name, func in sorted(self.commands.items()) if func.__doc__]
            help_string = header + "\n".join(summaries)
        else:
            cmd = args[0]
            if cmd in self.commands and self.commands[cmd].__doc__:
                docstring = self.commands[cmd].__doc__.strip()
                lines = docstring.splitlines()
                lines[0] = f"[bold]{lines[0]}[/bold]"
                help_string = "\n".join(line.strip() for line in lines)
            else:
                return (f"help: no help topics match `{cmd}`", "error")

        return (help_string, "output")

    def _cmd_clear(self, args: list[str]) -> None:
        """clear

        Clear the terminal screen.
        """
        # self.history_container.query(Static).remove() # to fix
        return None

    def _cmd_touch(self, args: list[str]) -> str:
        """touch <FILE>...

        Creates one or more empty files.
        """
        if not args:
            return "Usage: touch <file>..."
        for filename in args:
            self.vfs.touch(filename)
        return ""

    def _cmd_mkdir(self, args: list[str]) -> str:
        """mkdir [-p] <DIRECTORY>

        Create a new directory. If -p is given, create parent directories
        as needed without raising an error if they already exist.
        """
        if not args:
            return "Usage: mkdir [-p] <dir>"
        parents = "-p" in args
        if parents:
            args.remove("-p")
        self.vfs.mkdir(args[0], parents=parents)
        return ""

    def _cmd_rm(self, args: list[str]) -> str:
        """rm [-r] <FILE|DIRECTORY>

        Remove the specified file or directory. Use -r to remove
        directories and their contents recursively.
        """
        if not args:
            return "Usage: rm [-r] <path>..."
        recursive = "-r" in args
        if recursive:
            args.remove("-r")
        for path in args:
            self.vfs.rm(path, recursive=recursive)
        return ""

    def _cmd_pwd(self, args: list[str]) -> str:
        return self.vfs.cwd


class Dustty(Executable):
    APP_NAME = "Dustty"
    APP_ID = "terminal"

    @property
    def APP_ICON(self):
        return glyphs.icons.get("terminal", "?")
    MAIN_WIDGET = VFSTerminalWidget
