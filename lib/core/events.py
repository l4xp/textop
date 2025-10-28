from __future__ import annotations

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

# class Terminate(Message):
#     """A message to request terminating an existing window."""
#     def __init__(self, window: window, app_id):
#         log(f"Posting rquest to terminate {executable.app_name}.")
#         self.window = window
#         super().__init__()


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


class ActiveWindowsChanged(Message):
    """Posted when the set of active windows changes."""
    def __init__(self, active_windows: dict[str, list]) -> None:
        log(f"Active windows has change: {active_windows}.")
        self.active_windows = active_windows
        super().__init__()
