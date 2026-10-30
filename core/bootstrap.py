"""Loading the built-in capabilities.

The framework itself knows nothing about ping or DNS.  What it knows is how
to *hold* an operation.  This module is the bridge: it imports the
capability packages and registers what they define.

The import is deliberate and explicit rather than a filesystem scan.  An
explicit list means the set of built-in capabilities is a fact you can read,
a missing optional dependency degrades one capability instead of breaking
the import, and the bootstrap order is deterministic.
"""

from __future__ import annotations

import importlib
from types import ModuleType

from netforge.core.logging import get_logger
from netforge.registry.registry import OperationRegistry

__all__ = ["BUILTIN_MODULES", "load_builtin_operations", "builtin_registry"]

_logger = get_logger("core.bootstrap")

#: The capability modules that ship with the framework, in load order.
BUILTIN_MODULES: tuple[str, ...] = (
    "netforge.connectivity.tcp",
    "netforge.connectivity.udp",
    "netforge.connectivity.http",
    "netforge.connectivity.ssh",
    "netforge.connectivity.websocket",
    "netforge.discovery.ping",
    "netforge.discovery.sweep",
    "netforge.discovery.traceroute",
    "netforge.discovery.arp",
    "netforge.discovery.route",
    "netforge.discovery.service",
    "netforge.dns.resolver",
    "netforge.dns.diagnostics",
    "netforge.protocols.http",
    "netforge.protocols.mqtt",
    "netforge.protocols.snmp",
    "netforge.protocols.modbus",
    "netforge.protocols.opcua",
    "netforge.capture.session",
    "netforge.analysis.flow",
    "netforge.configuration.manager",
    "netforge.security.scanner",
    "netforge.security.banner",
    "netforge.security.tls",
    "netforge.security.headers",
    "netforge.sentinel.alerts",
    "netforge.sentinel.network",
    "netforge.sentinel.logs",
    "netforge.manipulation.proxy",
    "netforge.emulation.profile",
    "netforge.emulation.netem",
)


def _import(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except ImportError as exc:  # pragma: no cover - depends on the environment
        _logger.warning("built-in module %s could not be imported: %s", name, exc)
        return None


def load_builtin_operations(registry: OperationRegistry | None = None) -> OperationRegistry:
    """Register every built-in operation into ``registry``.

    A module that cannot be imported is logged and skipped: a missing
    optional dependency degrades one capability, it does not take the
    framework down.
    """
    registry = registry if registry is not None else OperationRegistry()
    for name in BUILTIN_MODULES:
        module = _import(name)
        if module is None:
            continue
        registry.register_module(module)
    _logger.info("loaded %d built-in operations", len(registry))
    return registry


def builtin_registry() -> OperationRegistry:
    """Return a fresh registry populated with the built-in operations."""
    return load_builtin_operations(OperationRegistry())
