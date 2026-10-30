"""The plugin system.

A plugin adds operations to NetForge.  It is discovered through the
``netforge.plugins`` entry point group or through a directory, and it is
loaded without the risk of taking the framework down.
"""

from __future__ import annotations

from netforge.plugins.base import Plugin, PluginError
from netforge.plugins.manager import ENTRY_POINT_GROUP, PluginManager, discover_plugins

__all__ = [
    "ENTRY_POINT_GROUP",
    "Plugin",
    "PluginError",
    "PluginManager",
    "discover_plugins",
]
