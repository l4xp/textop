import importlib
import inspect
import os
import shlex
import shutil
from pathlib import Path
from typing import TypedDict

from lib.display.window import Executable
from textual import log


class AppInfo(TypedDict):
    id: str
    name: str
    category: str
    cls: type[Executable]
    icon_name: str | None
    icon_override: str | None


class classproperty(property):
    """
    A decorator that combines @classmethod and @property.
    Allows a method to be accessed as a property of the class.
    """
    def __get__(self, cls, owner):
        return self.fget.__get__(None, owner)()


class VFS:
    """A Virtual File System to sandbox file operations."""

    def __init__(self, root: str):
        self.root_dir = Path(root).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.cwd = "/"

    @property
    def current_path(self) -> Path:
        """Returns the absolute, real path of the current virtual directory."""
        return self._get_safe_path(self.cwd)

    def _get_safe_path(self, user_path: str) -> Path:
        """
        Resolves a user-provided path against the virtual CWD and root.
        This is the core security function.
        """
        if user_path.startswith('/'):
            combined_path = self.root_dir / user_path.lstrip('/')
        else:
            combined_path = self.root_dir / self.cwd.lstrip('/') / user_path

        resolved_path = combined_path.resolve()

        # SECURITY CHECK: Ensure the final path is still inside our root.
        if self.root_dir not in resolved_path.parents and resolved_path != self.root_dir:
            raise PermissionError("Access denied: path is outside sandbox.")

        return resolved_path

    def discover_apps(self, directory: str = "bin") -> dict[str, list[AppInfo]]:
        """
        Scans a directory for Python files, finds subclasses of Executable,
        and returns them grouped by category.
        """
        categorized_apps: dict[str, list[AppInfo]] = {}
        base_path = Path(directory)

        for file_path in base_path.rglob("*.py"):
            if file_path.name.startswith("__"):
                continue

            module_str = ".".join(file_path.with_suffix("").parts)

            try:
                module = importlib.import_module(module_str)
                for _, member_class in inspect.getmembers(module, inspect.isclass):
                    if issubclass(member_class, Executable) and member_class is not Executable:
                        def get_class_attr(attr_name: str, default_value: any) -> any:
                            attr = getattr(member_class, attr_name, default_value)
                            if isinstance(attr, property):
                                log(
                                    f"App '{member_class.APP_NAME}' uses @property for '{attr_name}'. "
                                    f"Please use @classproperty or a static variable. "
                                    f"Using default value '{default_value}'."
                                )
                                return default_value
                            return attr
                        # --------------------------------
                        app_info: AppInfo = {
                            "id": getattr(member_class, "APP_ID", "unknown_id"),
                            "name": getattr(member_class, "APP_NAME", "Untitled App"),
                            "category": getattr(member_class, "APP_CATEGORY", "Miscellaneous"),
                            "cls": member_class,
                            "icon_name": getattr(member_class, "APP_ICON_NAME", None),
                            "icon_override": getattr(member_class, "APP_ICON_OVERRIDE", None)
                        }
                        category = app_info["category"]
                        if category not in categorized_apps:
                            categorized_apps[category] = []
                        categorized_apps[category].append(app_info)
            except Exception as e:
                log(f"Could not discover apps in {file_path}: {e}")

        return categorized_apps

    def cd(self, path: str) -> None:
        """Changes the virtual current working directory."""
        target_path = self._get_safe_path(path)
        if not target_path.is_dir():
            raise FileNotFoundError(f"Directory not found: {path}")

        # Store the new CWD as a relative virtual path
        self.cwd = "/" + target_path.relative_to(self.root_dir).as_posix()
        if self.cwd == "/.":
            self.cwd = "/"

    def ls(self, path: str = ".") -> list[str]:
        """Lists the contents of a virtual directory."""
        target_path = self._get_safe_path(path)
        if not target_path.is_dir():
            raise FileNotFoundError(f"Directory not found: {path}")
        return sorted(p.name for p in target_path.iterdir())

    def cat(self, path: str) -> str:
        """Returns the content of a file in the virtual file system."""
        target_path = self._get_safe_path(path)
        if not target_path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        return target_path.read_text()

    def touch(self, path: str) -> None:
        """Creates an empty file at the specified virtual path."""
        target_path = self._get_safe_path(path)
        target_path.touch()

    def mkdir(self, path: str, parents: bool = False) -> None:
        """Creates a directory within the sandbox."""
        target_path = self._get_safe_path(path)
        # Texist_ok=True prevents errors if the directory already exists
        target_path.mkdir(parents=parents, exist_ok=True)

    def rm(self, path: str, recursive: bool = False) -> None:
        """Removes a file or directory within the sandbox."""
        target_path = self._get_safe_path(path)
        if not target_path.exists():
            raise FileNotFoundError(f"Cannot remove '{path}': No such file or directory")

        if target_path.is_dir():
            if not recursive:
                raise IsADirectoryError(f"Cannot remove '{path}': Is a directory. Use -r.")
            shutil.rmtree(target_path)
        else:
            target_path.unlink()

    def write_file(self, path: str, content: str) -> None:
        """Writes content to a file, overwriting it if it exists."""
        target_path = self._get_safe_path(path)
        target_path.write_text(content)
