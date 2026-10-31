"""The LangChain adapter.

LangChain builds the schema of a tool from an ``args_schema``, which is
a Pydantic model.  The request model of an operation is therefore used
as it is: the arguments of the tool are validated against it, and the
schema the model is offered carries the types, the defaults and the
descriptions of the operation.

The mapping is one-to-one:

* an operation becomes a tool;
* the request model becomes the arguments of the tool;
* the response model becomes the return annotation.

``langchain-core`` is an optional extra and is imported lazily.
"""

from __future__ import annotations

from typing import Any

from netforge.adapters.base import Adapter, the_operation_caller
from netforge.core.exceptions import DependencyMissingError
from netforge.core.logging import get_logger
from netforge.registry.registry import OperationRegistry

__all__ = [
    "LangChainAdapter",
    "build_tools",
    "serve_langchain",
]

_logger = get_logger("adapters.langchain")

LANGCHAIN_EXTRA = "langchain"


def _load_langchain():
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise DependencyMissingError(
            "langchain-core",
            extra=LANGCHAIN_EXTRA,
            feature="the LangChain adapter",
        ) from exc
    from langchain_core.tools import StructuredTool

    return StructuredTool


class LangChainAdapter(Adapter):
    """The LangChain adapter."""

    name = "langchain"
    description = "Exposes the operations as LangChain tools."

    def __init__(self, registry: OperationRegistry | None = None) -> None:
        self.registry = registry if registry is not None else OperationRegistry()

    def available(self) -> bool:
        """Return ``True`` when langchain-core is installed."""
        try:
            _load_langchain()
        except DependencyMissingError:
            return False
        return True

    def unavailable_reason(self) -> str | None:
        """Return why the adapter is not available."""
        try:
            _load_langchain()
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
    """Build a LangChain tool for every operation in the registry."""
    structured_tool = _load_langchain()
    registry = registry if registry is not None else OperationRegistry()

    tools: list[Any] = []
    for descriptor in registry:
        operation_class = registry.get_operation(descriptor.name)

        # The caller is built here, so that it holds its own operation and
        # not the one the loop happened to leave behind.
        call = the_operation_caller(operation_class)

        tools.append(
            structured_tool.from_function(
                coroutine=call,
                name=descriptor.name,
                description=descriptor.summary or descriptor.description,
                args_schema=operation_class.request_model,
            )
        )
    return tools


def serve_langchain(registry: OperationRegistry | None = None) -> int:
    """Print the tools that the adapter would expose.

    There is no server here -- the tools are meant to be handed to an
    agent -- so the command prints them and stops.
    """
    tools = build_tools(registry)
    for tool in tools:
        print(f"{tool.name}\n    {tool.description}")
    print(f"\n{len(tools)} tool(s).")
    return 0
