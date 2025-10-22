class DusttyTerminal(Widget, can_focus=True):
    """
    A sandboxed terminal that uses a custom command parser and a
    Virtual File System.
    """
    MAX_HISTORY_LINES = 10000
    _blink = reactive(True)

    def __init__(self, vfs_root: str, **kwargs):
        super().__init__(**kwargs)
        self.vfs = VFS(vfs_root)
        self._history: list[Text] = []
        self._current_input: str = ""
        self._cursor_pos: int = 0
        self._command_history: list[str] = []
        self._history_cursor: int = 0
        self._draft_input: str | None = None
        self._scroll_offset: int = 0

        self.commands = {
            "ls": self._cmd_ls,
            "cd": self._cmd_cd,
            "cat": self._cmd_cat,
            "help": self._cmd_help,
            "clear": self._cmd_clear,
            "touch": self._cmd_touch,
            "mkdir": self._cmd_mkdir,
            "rm": self._cmd_rm,
            "pwd": self._cmd_pwd,
        }

    def on_unmount(self):
        if hasattr(self, "cursor_timer"):
            self.cursor_timer.cancel()

    def on_mount(self):
        """Welcome message and initial prompt."""
        welcome = [
            Text("Welcome to the Dustty Terminal!", style="bold green"),
            Text("Type 'help' for available commands.", style="bold green")
        ]
        self._history.extend(welcome)
        self.cursor_timer = self.set_interval(0.5, self._toggle_cursor)
        self.focus()

    def _toggle_cursor(self) -> None:
        if self.has_focus:
            self._blink = not self._blink
        else:
            self._blink = False

    def _get_prompt(self) -> Text:
        """Generates the command prompt."""
        return Text(f"guest:{self.vfs.cwd} $ ", style="bold blue")

    def on_key(self, event: events.Key) -> None:
        """The REPL: Read, Eval, Print Loop."""
        if event.key == "enter":
            if self._current_input:  # Don't save empty commands
                self._command_history.append(self._current_input)
            self._history_cursor = len(self._command_history)
            # --- EVAL ---
            self._execute_command(self._current_input)
            self._current_input = ""
            self._cursor_pos = 0
        elif event.key == "up":
            if self._history_cursor == len(self._command_history):
                # Save current input before browsing
                self._draft_input = self._current_input
            self._history_cursor = max(0, self._history_cursor - 1)
            if self._command_history:
                self._current_input = self._command_history[self._history_cursor]
                self._cursor_pos = len(self._current_input)
        elif event.key == "down":
            if self._history_cursor < len(self._command_history):
                self._history_cursor += 1
                if self._history_cursor == len(self._command_history):
                    # restore draft
                    self._current_input = self._draft_input or ""
                    self._draft_input = None
                else:
                    self._current_input = self._command_history[self._history_cursor]
                    self._cursor_pos = len(self._current_input)
        elif event.key == "left":
            self._cursor_pos = max(0, self._cursor_pos - 1)
        elif event.key == "right":
            self._cursor_pos = min(len(self._current_input), self._cursor_pos + 1)

        elif event.key == "backspace":
            if self._cursor_pos > 0:
                self._current_input = (
                    self._current_input[:self._cursor_pos - 1] +
                    self._current_input[self._cursor_pos:]
                )
                self._cursor_pos -= 1

        elif event.key == "delete":
            if self._cursor_pos < len(self._current_input):
                self._current_input = (
                    self._current_input[:self._cursor_pos] +
                    self._current_input[self._cursor_pos + 1:]
                )

        elif event.key in ("pageup", "pagedown"):
            half_height = self.size.height // 2
            self._scroll_by(half_height if event.key == "pageup" else -half_height)

        elif event.key == "tab":
            pass

        elif event.character:
            # --- READ ---
            self._current_input = (
                self._current_input[:self._cursor_pos] +
                event.character +
                self._current_input[self._cursor_pos:]
            )
            self._cursor_pos += 1
            self._scroll_offset = 0  # always reset to bottom

        # --- PRINT (via refresh) ---
        self._blink = True  # static on input
        self.cursor_timer.reset()  # Reset the timer
        self.refresh()

    def on_mouse_scroll_up(self) -> None:
        """Scroll the history buffer up."""
        self._scroll_by(1)

    def on_mouse_scroll_down(self) -> None:
        """Scroll the history buffer down."""
        self._scroll_by(-1)

    def _scroll_by(self, delta: int):
        """Adjusts scroll offset by delta, clamped to bounds."""
        visible_height = max(0, self.size.height - 1)
        max_scroll = max(0, len(self._history) - visible_height)
        self._scroll_offset = max(0, min(self._scroll_offset + delta, max_scroll))
        self.refresh()

    def _execute_command(self, command_str: str):
        """Parses, dispatches, and executes a command."""
        # Add the command itself to history
        prompt = self._get_prompt()
        self._history.append(prompt + command_str)

        if not command_str.strip():
            return

        try:
            parts = shlex.split(command_str)
            command_name = parts[0]
            args = parts[1:]

            if command_name in self.commands:
                output = self.commands[command_name](args)
            else:
                output = f"Command not found: {command_name}"

            if output:
                lines = str(output).split("\n")
                for line in lines:
                    self._history.append(Text(line))
                if len(self._history) > self.MAX_HISTORY_LINES:
                    self._history = self._history[-self.MAX_HISTORY_LINES:]

        except Exception as e:
            # Catch errors from VFS
            self._history.append(Text(str(e), style="bold red"))

        self._scroll_offset = 0  # always reset to bottom
        self.refresh()

    def render(self) -> Text:
        """Displays the visible portion of the history and the current input line."""
        total_lines = len(self._history)
        show_prompt = self._scroll_offset == 0

        # Reserve 1 line for prompt only when visible
        visible_height = max(1, self.size.height - (1 if show_prompt else 0))
        max_scroll = max(0, total_lines - visible_height)
        self._scroll_offset = max(0, min(self._scroll_offset, max_scroll))

        view_end = total_lines - self._scroll_offset
        view_start = max(0, view_end - visible_height)
        visible_history = self._history[view_start:view_end]
        history_text = Text("\n").join(visible_history)

        if show_prompt:
            prompt_text = self._get_prompt()
            before = Text(self._current_input[:self._cursor_pos])
            if self._cursor_pos < len(self._current_input):
                # Cursor is on top of an existing character
                cursor = Text(self._current_input[self._cursor_pos], style="reverse" if self._blink else "")
                after = Text(self._current_input[self._cursor_pos + 1:])
            else:
                # Cursor at the end
                cursor = Text(" ", style="reverse" if self._blink else "")
                after = Text("")
            if history_text:
                body = history_text + "\n"
            else:
                body = Text("")
            return body + prompt_text + before + cursor + after
        return history_text

    # --- Commands ---
    def _cmd_ls(self, args: list[str]) -> str:
        """ls [PATH]

        List directory contents. If PATH is not specified, lists
        the contents of the current directory.
        """
        path = args[0] if args else "."
        try:
            contents = self.vfs.ls(path)
            return "\n".join(contents)
        except Exception as e:
            return str(e)

    def _cmd_cd(self, args: list[str]) -> str:
        """cd <DIRECTORY>

        Change the current working directory to DIRECTORY.
        """
        if not args:
            return "Usage: cd <directory>"
        try:
            self.vfs.cd(args[0])
            return ""
        except Exception as e:
            return str(e)

    def _cmd_cat(self, args: list[str]) -> str:
        """cat <FILE>

        Display the contents of a file.
        """
        if not args:
            return "Usage: cat <file>"
        try:
            return self.vfs.cat(args[0])
        except Exception as e:
            return str(e)

    def _cmd_help(self, args: list[str]) -> str:
        """help [COMMAND]

        Display helpful information about built-in commands.
        If COMMAND is specified, gives detailed help on that command.
        """
        if not args:
            # --- GENERAL HELP ---
            # Display the formatted list of all available commands.
            header = (
                "Sandboxed Shell, version 1.0\n"
                "These shell commands are defined internally. Type `help` to see this list.\n"
                "Type `help name` to find out more about the command `name`.\n"
            )

            command_list = []
            for name, func in sorted(self.commands.items()):
                summary = func.__doc__.strip().split('\n')[0] if func.__doc__ else "No summary available."
                command_list.append(f"  {name:<15} {summary}")

            return header + "\n".join(command_list)

        else:
            # --- SPECIFIC HELP ---
            # Display the full docstring for a single command.
            command_name = args[0]
            if command_name in self.commands:
                func = self.commands[command_name]
                docstring = func.__doc__.strip() if func.__doc__ else f"No help available for {command_name}"
                return "\n".join(line.strip() for line in docstring.split('\n'))
            else:
                return f"help: no help topics match `{command_name}`. Try `help`."

    def _cmd_clear(self, args: list[str]) -> str:
        """clear

        Clear the terminal screen.
        """
        self._history.clear()
        return ""

    def _cmd_touch(self, args: list[str]) -> str:
        """touch <FILE>...

        Creates one or more empty files.
        """
        if not args:
            return "Usage: touch <filename>"
        try:
            for filename in args:
                self.vfs.touch(filename)
            return ""
        except Exception as e:
            return str(e)

    def _cmd_mkdir(self, args: list[str]) -> str:
        """mkdir [-p] <DIRECTORY>

        Create a new directory. If -p is given, create parent directories
        as needed without raising an error if they already exist.
        """
        if not args:
            return "Usage: mkdir [-p] <directory_name>"

        parents = False
        path_arg = args[0]
        if args[0] == "-p":
            if len(args) < 2:
                return "Usage: mkdir [-p] <directory_name>"
            parents = True
            path_arg = args[1]

        try:
            self.vfs.mkdir(path_arg, parents=parents)
            return ""
        except Exception as e:
            return str(e)

    def _cmd_rm(self, args: list[str]) -> str:
        """rm [-r] <FILE|DIRECTORY>

        Remove the specified file or directory. Use -r to remove
        directories and their contents recursively.
        """
        if not args:
            return "Usage: rm [-r] <file_or_directory>"

        recursive = False
        paths_to_delete = []
        if "-r" in args:
            recursive = True
            args.remove("-r")

        paths_to_delete = args
        if not paths_to_delete:
            return "No file specified."

        for path in paths_to_delete:
            try:
                self.vfs.rm(path, recursive=recursive)
            except Exception as e:
                return str(e)
        return ""

    def _cmd_pwd(self, args: list[str]) -> str:
        """pwd

        Print the current working directory.
        """
        return self.vfs.cwd


class TerminalSetup(Container):
    def compose(self):
        yield DusttyTerminal(vfs_root="./vdisk")
