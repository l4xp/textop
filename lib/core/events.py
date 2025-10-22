from __future__ import annotations

from lib.display.window import Executable
from textual import log
from textual.message import Message

# =============================================================================
# Custom Messages
# =============================================================================


class Run(Message):
    """A message to request opening a new application window."""
    def __init__(self, executable: Executable):
        log(f"Posting request to run {executable.app_name}.")
        self.executable = executable
        super().__init__()


class ChangeWindowMode(Message):
    """A message to request window layout changes."""
    def __init__(self, mode: str):
        log(f"Posting request to change window mode to {mode}.")
        self.mode = mode
        super().__init__()


class WMLayoutChanged(Message):
    """Fired when wm changes layout"""
    def __init__(self, mode: str):
        self.mode = mode
        super().__init__()
