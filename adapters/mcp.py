"""The MCP adapter.

MCP -- the Model Context Protocol -- exposes NetForge's operations as
tools.  The mapping is one-to-one:

* an operation becomes a tool;
* the operation's request model becomes the tool's input schema;
* the operation's summary becomes the tool's description;
* the operation's risk level is reported in the description, so that a
  model can see what it is about to do.

The ``mcp`` package is an optional extra and is imported lazily.
"""

from __future__ import annotations

from typing import Any

from netforge.adapters.base import (
    Adapter,
    AdapterError,
    the_operation_caller,
    the_request_signature,
)
from netforge.core.exceptions import DependencyMissingError
from netforge.core.logging import get_logger
from netforge.registry.registry import OperationRegistry

__all__ = ["McpAdapter", "build_server", "serve_mcp", "tool_description"]

_logger = get_logger("adapters.mcp")

MCP_EXTRA = "mcp"


def _load_mcp() -> Any:
    """Return the server class of the installed MCP SDK.

    The class was renamed in mcp 2.x: ``FastMCP`` became ``MCPServer`` and
    moved from ``mcp.server.fastmcp`` to ``mcp.server.mcpserver``.  Both
    spellings are tried, newest first, so the adapter works with either
    version of the extra.

    The class is what the adapter really needs, so the loader reports a
    missing dependency when the *package* is absent, and an unusable
    version when the package is there but the class is not.  An adapter
    that says it is available and then fails to build a server is worse
    than one that says it is not.
    """
    try:
        import mcp  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise DependencyMissingError(
            "mcp",
            extra=MCP_EXTRA,
            feature="the MCP adapter",
        ) from exc

    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError:
        try:
            from mcp.server.fastmcp import FastMCP
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise AdapterError(
                "the installed version of mcp has neither MCPServer nor FastMCP; "
                "the MCP adapter needs mcp 1.x or mcp 2.x"
            ) from exc
        return FastMCP
    return MCPServer


def tool_description(descriptor: Any) -> str:
    """Return the description of an MCP tool for an operation descriptor."""
    lines = [
        descriptor.summary or descriptor.name,
        "",
        f"Risk level: L{descriptor.risk_level} ({descriptor.risk_level.label}).",
    ]
    if descriptor.requires_privilege:
        lines.append("This operation needs elevated privileges.")
    if descriptor.description:
        lines.extend(["", descriptor.description])
    return "\n".join(lines)


class McpAdapter(Adapter):
    """The MCP adapter."""

    name = "mcp"
    description = "Exposes the operations as MCP tools."

    def __init__(self, registry: OperationRegistry | None = None) -> None:
        self.registry = registry if registry is not None else OperationRegistry()

    def available(self) -> bool:
        """Return ``True`` when the MCP server class can be loaded."""
        try:
            _load_mcp()
        except (DependencyMissingError, AdapterError):
            return False
        return True

    def unavailable_reason(self) -> str | None:
        """Return why the adapter is not available."""
        try:
            _load_mcp()
        except (DependencyMissingError, AdapterError) as exc:
            return str(exc)
        return None

    def describe(self) -> dict[str, Any]:
        """Return a description of the adapter."""
        return {
            "name": self.name,
            "description": self.description,
            "available": self.available(),
            "operations": len(self.registry),
            "reason": self.unavailable_reason(),
        }


def build_server(registry: OperationRegistry | None = None) -> Any:
    """Build the MCP server over the registry."""
    server_class = _load_mcp()
    registry = registry if registry is not None else OperationRegistry()
    server = server_class("netforge")

    for descriptor in registry:
        operation_class = registry.get_operation(descriptor.name)

        # The caller is built here, so that it holds its own operation and
        # not the one the loop happened to leave behind.
        call = the_operation_caller(operation_class)
        # The SDK derives the input schema from the signature of the
        # function, so the request model is given to it as one.
        call.__signature__ = the_request_signature(operation_class.request_model)
        call.__name__ = descriptor.name.replace(".", "_")
        call.__doc__ = tool_description(descriptor)

        server.add_tool(
            fn=call,
            name=descriptor.name,
            description=tool_description(descriptor),
        )
        _logger.debug("exposed %s as an MCP tool", descriptor.name)

    return server


def serve_mcp(registry: OperationRegistry | None = None) -> int:
    """Serve the MCP server over stdio and block until it is interrupted."""
    server = build_server(registry)
    server.run()
    return 0
