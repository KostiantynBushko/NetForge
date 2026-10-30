"""The plugin system.

A plugin is a package that adds operations to NetForge.  It is discovered
in one of two ways:

* through the ``netforge.plugins`` entry point group, which is how a
  distributed package advertises itself;
* through a directory, which is how a local, unpacked plugin is loaded.

Either way, the plugin is a class with a name, a version and a list of
operations.  The manager instantiates it, calls :meth:`Plugin.operations`
and registers what it gets.

A plugin that fails to load is reported and skipped.  It never takes the
framework down -- a broken third-party plugin must not be able to stop an
operator from running ``ping``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.registry.descriptor import OperationDescriptor
from netforge.registry.registry import OperationRegistry

__all__ = ["Plugin", "PluginError"]

_logger = get_logger("plugins.base")


class PluginError(Exception):
    """A plugin could not be loaded."""


class Plugin(ABC):
    """Base class of every NetForge plugin."""

    #: The name of the plugin.
    name: ClassVar[str] = ""

    #: The version of the plugin.
    version: ClassVar[str] = "0.0.0"

    #: A one-line description of what the plugin adds.
    description: ClassVar[str] = ""

    @abstractmethod
    def operations(self) -> list[type[Operation]]:
        """Return the operation classes the plugin provides."""

    def register(self, registry: OperationRegistry) -> list[OperationDescriptor]:
        """Register the plugin's operations into ``registry``."""
        descriptors: list[OperationDescriptor] = []
        for operation in self.operations():
            descriptors.append(registry.register(operation))
        return descriptors

    def describe(self) -> dict[str, str]:
        """Return a description of the plugin."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
        }
