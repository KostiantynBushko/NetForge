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

import json
from typing import Any

from netforge.adapters.base import Adapter
from netforge.core.exceptions import DependencyMissingError
from netforge.core.logging import get_logger
from netforge.registry.registry import OperationRegistry

__all__ = ["McpAdapter", "build_server", "serve_mcp", "tool_description"]

_logger = get_logger("adapters.mcp")

MCP_EXTRA = "mcp"


def _load_mcp():
    try:
        import mcp
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise DependencyMissingError(
            "mcp",
            extra=MCP_EXTRA,
            feature="the MCP adapter",
        ) from exc
    import mcp

    return mcp


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
        """Return ``True`` when the mcp package is installed."""
        try:
            _load_mcp()
        except DependencyMissingError:
            return False
        return True

    def unavailable_reason(self) -> str | None:
        """Return why the adapter is not available."""
        try:
            _load_mcp()
        except DependencyMissingError as exc:
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
    mcp = _load_mcp()
    from mcp.server.fastmcp import FastMCP

    registry = registry if registry is not None else OperationRegistry()
    server = FastMCP("netforge")

    for descriptor in registry:
        operation_class = registry.get_operation(descriptor.name)
        input_schema = descriptor.request_schema

        async def _call(payload: dict[str, Any], _cls: Any = operation_class) -> str:
            operation = _cls()
            response = await operation.run_request(payload)
            return json.dumps(response.model_dump(mode="json"), indent=2)

        server.add_tool(
            descriptor.name,
            description=tool_description(descriptor),
            fn=_call,
        )
        _logger.debug("exposed %s as an MCP tool", descriptor.name)

    return server


def serve_mcp(registry: OperationRegistry | None = None) -> int:
    """Serve the MCP server over stdio and block until it is interrupted."""
    server = build_server(registry)
    server.run()
    return 0
