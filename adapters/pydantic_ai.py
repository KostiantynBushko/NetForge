"""The Pydantic AI adapter.

Pydantic AI is an agent framework built on Pydantic, so the request
model of an operation can be the parameter of the tool itself.  The
framework validates the arguments of the tool against that model and
flattens it into the schema the model is offered, which keeps the types,
the defaults and the descriptions of the operation exactly as they are
declared.

The mapping is one-to-one:

* an operation becomes a tool;
* the request model becomes the parameter of the tool;
* the response model becomes the return annotation.

``pydantic-ai`` is an optional extra and is imported lazily.
"""

from __future__ import annotations

from typing import Any

from netforge.adapters.base import Adapter, the_request_caller
from netforge.core.exceptions import DependencyMissingError
from netforge.core.logging import get_logger
from netforge.registry.registry import OperationRegistry

__all__ = [
    "PydanticAiAdapter",
    "build_agent",
    "build_tools",
    "serve_pydantic_ai",
]

_logger = get_logger("adapters.pydantic_ai")

PYDANTIC_AI_EXTRA = "pydantic-ai"


def _load_pydantic_ai():
    try:
        from pydantic_ai import Agent, Tool
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise DependencyMissingError(
            "pydantic-ai",
            extra=PYDANTIC_AI_EXTRA,
            feature="the Pydantic AI adapter",
        ) from exc
    from pydantic_ai import Agent, Tool

    return Agent, Tool


class PydanticAiAdapter(Adapter):
    """The Pydantic AI adapter."""

    name = "pydantic-ai"
    description = "Exposes the operations as Pydantic AI tools."

    def __init__(self, registry: OperationRegistry | None = None) -> None:
        self.registry = registry if registry is not None else OperationRegistry()

    def available(self) -> bool:
        """Return ``True`` when pydantic-ai is installed."""
        try:
            _load_pydantic_ai()
        except DependencyMissingError:
            return False
        return True

    def unavailable_reason(self) -> str | None:
        """Return why the adapter is not available."""
        try:
            _load_pydantic_ai()
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
    """Build a Pydantic AI tool for every operation in the registry."""
    _, tool_class = _load_pydantic_ai()
    registry = registry if registry is not None else OperationRegistry()

    tools: list[Any] = []
    for descriptor in registry:
        operation_class = registry.get_operation(descriptor.name)

        # The caller is built here, so that it holds its own operation and
        # not the one the loop happened to leave behind.  Its parameter is
        # the request model, which is what the framework validates against.
        call = the_request_caller(operation_class, operation_class.request_model)

        tools.append(
            tool_class(
                call,
                name=descriptor.name,
                description=descriptor.summary or descriptor.description,
            )
        )
    return tools


def build_agent(
    registry: OperationRegistry | None = None,
    model: Any = None,
    **kwargs: Any,
) -> Any:
    """Build a Pydantic AI agent with a tool for every operation.

    The model is the one of the agent, and may be left out -- Pydantic AI
    then asks for one when the agent is run.
    """
    agent_class, _ = _load_pydantic_ai()
    tools = build_tools(registry)
    return agent_class(model, tools=tools, **kwargs)


def serve_pydantic_ai(registry: OperationRegistry | None = None) -> int:
    """Print the tools that the adapter would expose.

    There is no server here -- the tools are meant to be handed to an
    agent -- so the command prints them and stops.
    """
    tools = build_tools(registry)
    for tool in tools:
        print(f"{tool.name}\n    {tool.description}")
    print(f"\n{len(tools)} tool(s).")
    return 0
