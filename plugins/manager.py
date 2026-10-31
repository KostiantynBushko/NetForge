"""Discovering and loading plugins.

The manager knows three sources of plugins:

``entry_points``
    The ``netforge.plugins`` entry point group.  This is how a plugin
    that is installed as a distribution advertises itself.

``directory``
    A directory of Python packages.  This is how a plugin that is not
    installed -- a checkout, a folder on a USB stick -- is loaded.

``builtin``
    The plugins that ship with NetForge itself.  There are none yet, but
    the hook is here so that a built-in plugin is not a special case.

Every loader reports what it loaded and what it failed to load.  A failure
is never fatal: the manager collects it and carries on.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType
from typing import Any

from netforge.core.logging import get_logger
from netforge.plugins.base import Plugin
from netforge.registry.registry import OperationRegistry

__all__ = ["ENTRY_POINT_GROUP", "PluginManager"]

_logger = get_logger("plugins.manager")

#: The entry point group a distributed plugin advertises itself in.
ENTRY_POINT_GROUP = "netforge.plugins"


class PluginManager:
    """Loads plugins and registers their operations."""

    def __init__(self, registry: OperationRegistry | None = None) -> None:
        self.registry = registry if registry is not None else OperationRegistry()
        self._plugins: list[Plugin] = []
        self._failures: list[dict[str, str]] = []

    # -- sources ------------------------------------------------------------

    def load_entry_points(self, group: str = ENTRY_POINT_GROUP) -> list[Plugin]:
        """Load the plugins advertised in an entry point group."""
        loaded: list[Plugin] = []
        try:
            from importlib.metadata import entry_points
        except ImportError:  # pragma: no cover - Python < 3.8
            return loaded

        try:
            points = entry_points(group=group)
        except TypeError:  # pragma: no cover - Python 3.9 and older
            points = entry_points().get(group, [])  # type: ignore[attr-defined]

        for point in points:
            plugin = self._instantiate(point.load(), f"{group}:{point.name}")
            if plugin is not None:
                loaded.append(plugin)
        return loaded

    def load_directory(self, path: str | Path) -> list[Plugin]:
        """Load the plugins found in a directory.

        Every subdirectory that holds an ``__init__.py`` is treated as a
        plugin package, and every plugin class inside it is loaded.
        """
        loaded: list[Plugin] = []
        root = Path(path).expanduser()
        if not root.is_dir():
            self._failures.append({"source": str(root), "error": "the directory does not exist"})
            return loaded

        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or not (entry / "__init__.py").is_file():
                continue
            module = self._import_directory_package(entry)
            if module is None:
                continue
            for plugin in self._plugins_in_module(module, str(entry)):
                loaded.append(plugin)
        return loaded

    def load_builtins(self) -> list[Plugin]:
        """Load the plugins that ship with NetForge."""
        return []

    # -- registration -------------------------------------------------------

    def register(self, plugin: Plugin) -> list[Any]:
        """Register a plugin's operations into the registry."""
        try:
            descriptors = plugin.register(self.registry)
        except Exception as exc:  # noqa: BLE001 - a broken plugin must not break the load
            self._failures.append({"source": plugin.name or type(plugin).__name__, "error": str(exc)})
            _logger.warning("the plugin %s could not be registered: %s", plugin.name, exc)
            return []

        self._plugins.append(plugin)
        _logger.info(
            "the plugin %s %s registered %d operations",
            plugin.name,
            plugin.version,
            len(descriptors),
        )
        return descriptors

    def load_all(
        self,
        *,
        directories: Iterable[str | Path] = (),
        entry_point_group: str = ENTRY_POINT_GROUP,
        use_entry_points: bool = True,
    ) -> list[Plugin]:
        """Load every plugin from every source and register them."""
        loaded: list[Plugin] = []
        if use_entry_points:
            loaded.extend(self.load_entry_points(entry_point_group))
        for directory in directories:
            loaded.extend(self.load_directory(directory))
        loaded.extend(self.load_builtins())

        for plugin in loaded:
            self.register(plugin)
        return loaded

    # -- reporting ----------------------------------------------------------

    @property
    def plugins(self) -> list[Plugin]:
        """Return the plugins that were loaded."""
        return list(self._plugins)

    @property
    def failures(self) -> list[dict[str, str]]:
        """Return the plugins that could not be loaded, and why."""
        return list(self._failures)

    def describe(self) -> list[dict[str, str]]:
        """Return a description of every loaded plugin."""
        return [plugin.describe() for plugin in self._plugins]

    # -- internals ----------------------------------------------------------

    def _instantiate(self, factory: Any, source: str) -> Plugin | None:
        try:
            candidate = factory()
        except Exception as exc:  # noqa: BLE001 - a broken plugin must not break the load
            self._failures.append({"source": source, "error": str(exc)})
            _logger.warning("the plugin %s could not be loaded: %s", source, exc)
            return None

        if isinstance(candidate, Plugin):
            return candidate
        if isinstance(candidate, type) and issubclass(candidate, Plugin):
            try:
                return candidate()
            except Exception as exc:  # noqa: BLE001
                self._failures.append({"source": source, "error": str(exc)})
                _logger.warning("the plugin %s could not be instantiated: %s", source, exc)
                return None

        self._failures.append(
            {"source": source, "error": "the entry point did not resolve to a Plugin"}
        )
        return None

    def _import_directory_package(self, directory: Path) -> ModuleType | None:
        module_name = f"netforge_plugin_{directory.name.replace('-', '_')}"
        try:
            spec = importlib.util.spec_from_file_location(
                module_name, directory / "__init__.py", submodule_search_locations=[str(directory)]
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"the package {directory} has no importable __init__.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return module
        except Exception as exc:  # noqa: BLE001 - a broken plugin must not break the load
            self._failures.append({"source": str(directory), "error": str(exc)})
            _logger.warning("the plugin directory %s could not be loaded: %s", directory, exc)
            return None

    def _plugins_in_module(self, module: ModuleType, source: str) -> list[Plugin]:
        found: list[Plugin] = []
        for attribute in vars(module).values():
            if not isinstance(attribute, type) or not issubclass(attribute, Plugin):
                continue
            if attribute is Plugin or attribute.__module__ != module.__name__:
                continue
            try:
                found.append(attribute())
            except Exception as exc:  # noqa: BLE001
                self._failures.append({"source": source, "error": str(exc)})
                _logger.warning("the plugin %s could not be instantiated: %s", attribute.__name__, exc)
        return found


def discover_plugins(
    registry: OperationRegistry | None = None,
    *,
    directories: Iterable[str | Path] = (),
) -> PluginManager:
    """Load every plugin that can be found and return the manager."""
    manager = PluginManager(registry)
    manager.load_all(directories=directories)
    return manager
