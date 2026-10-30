"""NetForge -- a modular network operations and security toolkit.

NetForge provides reusable networking capabilities and exposes them through
Python, a command line, a REST API, MCP and LlamaIndex function tools --
without implementing any capability twice.

The framework is *first*: it depends on Pydantic and the standard library
and nothing else.  Every ecosystem integration is an optional extra.

The public API is small:

.. code-block:: python

    from netforge import ExecutionContext, load_builtin_operations

    registry = load_builtin_operations()
    operation = registry.create("discovery.ping")
    response = await operation.run(host="10.0.0.1")
"""

from __future__ import annotations

from typing import Any

__version__ = "0.1.0"

from netforge.core.config import NetForgeConfig
from netforge.core.context import Credential, ExecutionContext
from netforge.core.exceptions import (
    ConfigurationError,
    DependencyMissingError,
    NetForgeError,
    OperationExecutionError,
    OperationNotFoundError,
    PluginError,
    RiskPolicyError,
)
from netforge.core.logging import configure_logging, get_logger
from netforge.core.native import NativeImplementation, native_registry
from netforge.core.operation import Operation
from netforge.core.runner import CommandResult, CommandRunner, SubprocessCommandRunner
from netforge.models.base import NetForgeModel, RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.result import OperationMeta, OperationResult
from netforge.models.risk import RiskLevel
from netforge.registry.descriptor import OperationDescriptor
from netforge.registry.registry import OperationRegistry

__all__ = [
    "CapabilityCategory",
    "CommandResult",
    "CommandRunner",
    "ConfigurationError",
    "Credential",
    "DependencyMissingError",
    "ExecutionContext",
    "NetForgeConfig",
    "NetForgeError",
    "NetForgeModel",
    "NativeImplementation",
    "Operation",
    "OperationDescriptor",
    "OperationExecutionError",
    "OperationMeta",
    "OperationNotFoundError",
    "OperationRegistry",
    "OperationResult",
    "PluginError",
    "RequestModel",
    "ResponseModel",
    "RiskLevel",
    "RiskPolicyError",
    "SubprocessCommandRunner",
    "__version__",
    "configure_logging",
    "get_logger",
    "load_builtin_operations",
    "native_registry",
]


def load_builtin_operations(registry: OperationRegistry | None = None) -> OperationRegistry:
    """Register every built-in operation into ``registry``.

    This is a thin wrapper over :func:`netforge.core.bootstrap.load_builtin_operations`,
    exposed at the top level because it is the entry point most callers
    need.
    """
    from netforge.core.bootstrap import load_builtin_operations as _load

    return _load(registry)


def __getattr__(name: str) -> Any:
    """Expose the lazily imported parts of the public API."""
    if name == "PluginManager":
        from netforge.plugins.manager import PluginManager

        return PluginManager
    if name == "discover_plugins":
        from netforge.plugins.manager import discover_plugins

        return discover_plugins
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
