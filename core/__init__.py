"""The core of NetForge.

This package holds the framework itself: the operation contract, the
execution context, the configuration, the exception hierarchy and the
command runner.  It has no dependency on any capability package and no
dependency on any adapter.
"""

from __future__ import annotations

from netforge.core.config import ENV_PREFIX, NetForgeConfig
from netforge.core.context import Credential, ExecutionContext
from netforge.core.exceptions import (
    ConfigurationError,
    DependencyMissingError,
    NetForgeError,
    OperationExecutionError,
    OperationNotFoundError,
    PluginError,
    RiskPolicyError,
    TimeoutError,
)
from netforge.core.logging import configure_logging, get_logger
from netforge.core.native import NativeImplementation, NativeRegistry, native_registry
from netforge.core.operation import Operation
from netforge.core.runner import CommandResult, CommandRunner, SubprocessCommandRunner

__all__ = [
    "CommandResult",
    "CommandRunner",
    "ConfigurationError",
    "Credential",
    "DependencyMissingError",
    "ENV_PREFIX",
    "ExecutionContext",
    "NetForgeConfig",
    "NetForgeError",
    "NativeImplementation",
    "NativeRegistry",
    "Operation",
    "OperationExecutionError",
    "OperationNotFoundError",
    "PluginError",
    "RiskPolicyError",
    "SubprocessCommandRunner",
    "TimeoutError",
    "configure_logging",
    "get_logger",
    "native_registry",
]
