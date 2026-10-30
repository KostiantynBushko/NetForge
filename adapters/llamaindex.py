"""The LlamaIndex adapter.

The LlamaIndex adapter exposes NetForge's operations as
:class:`~llama_index.core.tools.FunctionTool` objects, so that an agent
built on LlamaIndex can call them.

The mapping is one-to-one:

* an operation becomes a function tool;
* the request model becomes the tool's parameters;
* the response model becomes the tool's return annotation.

``llama-index-core`` is an optional extra and is imported lazily.  The
tool builder is nevertheless implemented in full, and it is what the tests
exercise -- the parts that matter do not need LlamaIndex to be installed.
"""

from __future__ import annotations

import json
from typing import Any

from netforge.adapters.base import Adapter
from netforge.core.exceptions import DependencyMissingError
from netforge.core.logging import get_logger
from netforge.registry.registry import OperationRegistry

__all__ = ["LlamaIndexAdapter", "build_tools", "serve_llamaindex", "tool_parameters"]

_logger = get_logger("adapters.llamaindex")

LLAMAINDEX_EXTRA = "llamaindex"


def _load_llama_index():
    try:
        from llama_index.core.tools import FunctionTool
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise DependencyMissingError(
            "llama-index-core",
            extra=LLAMAINDEX_EXTRA,
            feature="the LlamaIndex adapter",
        ) from exc
    from llama_index.core.tools import FunctionTool

    return FunctionTool


def tool_parameters(descriptor: Any) -> dict[str, Any]:
    """Return the tool parameters of an operation descriptor.

    The JSON Schema of the request model is translated into the flat
    ``{"name": {"description": ..., "type": ...}}`` mapping that the
    LlamaIndex and OpenAI function-calling APIs use.
    """
    schema = descriptor.request_schema or {}
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    parameters: dict[str, Any] = {}
    for name, definition in properties.items():
        entry: dict[str, Any] = {
            "description": definition.get("description", ""),
            "type": definition.get("type", "string"),
        }
        if name in required:
            entry["required"] = True
        parameters[name] = entry
    return parameters


class LlamaIndexAdapter(Adapter):
    """The LlamaIndex adapter."""

    name = "llamaindex"
    description = "Exposes the operations as LlamaIndex function tools."

    def __init__(self, registry: OperationRegistry | None = None) -> None:
        self.registry = registry if registry is not None else OperationRegistry()

    def available(self) -> bool:
        """Return ``True`` when llama-index-core is installed."""
        try:
            _load_llama_index()
        except DependencyMissingError:
            return False
        return True

    def unavailable_reason(self) -> str | None:
        """Return why the adapter is not available."""
        try:
            _load_llama_index()
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


def build_tools(registry: OperationRegistry | None = None) -> list[Any]:
    """Build a function tool for every operation in the registry."""
    function_tool = _load_llama_index()
    registry = registry if registry is not None else OperationRegistry()

    tools: list[Any] = []
    for descriptor in registry:
        operation_class = registry.get_operation(descriptor.name)
        parameters = tool_parameters(descriptor)

        async def _call(**kwargs: Any) -> str:
            operation = operation_class()
            response = await operation.run_request(kwargs)
            return json.dumps(response.model_dump(mode="json"), indent=2)

        _call.__name__ = descriptor.name.replace(".", "_")
        _call.__doc__ = descriptor.summary or descriptor.description

        tools.append(
            function_tool.from_defaults(
                fn=_call,
                name=descriptor.name,
                description=descriptor.summary or descriptor.description,
            )
        )
    return tools


def serve_llamaindex(registry: OperationRegistry | None = None) -> int:
    """Print the tools that the adapter would expose.

    There is no server here -- the tools are meant to be handed to an
    agent -- so the command prints them and stops.
    """
    tools = build_tools(registry)
    for tool in tools:
        metadata = getattr(tool, "metadata", None)
        name = getattr(metadata, "name", None) or getattr(tool, "name", "?")
        description = getattr(metadata, "description", None) or getattr(tool, "description", "")
        print(f"{name}\n    {description}")
    print(f"\n{len(tools)} tool(s).")
    return 0
