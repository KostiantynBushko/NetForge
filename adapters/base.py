"""The adapter layer.

An adapter exposes NetForge to a consumer.  The framework itself knows
nothing about the consumer's world: no HTTP, no MCP, no LlamaIndex.

The contract is small, and it is the same for every adapter:

* an adapter *describes* itself -- its name, whether it is usable in this
  installation, what it can do;
* an adapter *lists* the operations;
* an adapter *invokes* an operation.

The CLI adapter is always available, because it is built on the standard
library.  The REST, MCP and LlamaIndex adapters need their extra, and they
say so when it is missing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from typing import Any

from netforge.core.exceptions import DependencyMissingError
from netforge.core.logging import get_logger
from netforge.models.risk import RiskLevel

__all__ = ["Adapter", "AdapterError", "find_missing_dependencies"]

_logger = get_logger("adapters.base")


class AdapterError(Exception):
    """An adapter could not do what it was asked to do."""


def find_missing_dependencies(
    requirements: Iterable[tuple[str, Callable[[], Any]]],
) -> list[str]:
    """Return the names of the optional dependencies that are not installed.

    ``requirements`` is a sequence of ``(name, loader)`` pairs.  Every
    loader is called, so that one call reports *all* of the dependencies
    that are missing rather than only the first.  An extra that provides
    several packages should be installed once, not once per package.
    """
    missing: list[str] = []
    for name, loader in requirements:
        try:
            loader()
        except DependencyMissingError:
            missing.append(name)
    return missing


class Adapter(ABC):
    """Base class of every NetForge adapter."""

    #: The name of the adapter.
    name: str = "adapter"

    #: A one-line description of what the adapter exposes.
    description: str = ""

    #: The risk level the adapter itself operates at.
    risk_level: RiskLevel = RiskLevel.SAFE

    @abstractmethod
    def available(self) -> bool:
        """Return ``True`` when the adapter can be used in this installation."""

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Return a description of the adapter."""

    def unavailable_reason(self) -> str | None:
        """Return why the adapter is not available, or ``None`` when it is."""
        return None
