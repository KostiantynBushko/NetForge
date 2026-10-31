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

import inspect
import json
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from netforge.core.exceptions import DependencyMissingError
from netforge.core.logging import get_logger
from netforge.models.risk import RiskLevel

__all__ = [
    "Adapter",
    "AdapterError",
    "find_missing_dependencies",
    "the_operation_caller",
    "the_request_signature",
]

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


def the_operation_caller(operation_class: type[Any]) -> Callable[..., Awaitable[str]]:
    """Return the coroutine that runs one operation and reports its result.

    The operation class is bound when the caller is *built*, not when it
    is called.  A closure over a variable of a loop resolves every caller
    to the last operation of that loop, because the variable is rebound
    once and the closure reads whatever it holds when it is finally
    called.  An adapter that exposes many operations cannot afford that:
    every tool would run the same operation.
    """
    async def call(**kwargs: Any) -> str:
        operation = operation_class()
        response = await operation.run_request(kwargs)
        return json.dumps(response.model_dump(mode="json"), indent=2)

    return call


def the_request_signature(request_model: type[Any]) -> inspect.Signature:
    """Return the signature of the request model of an operation.

    A framework that derives the schema of a tool from the signature of
    the function behind it has to be told what the parameters are.  The
    request model already knows: its fields become the parameters of the
    caller, with the types, the defaults and the required ones kept.
    """
    parameters: list[inspect.Parameter] = []
    for name, field in request_model.model_fields.items():
        annotation = field.annotation if field.annotation is not None else Any
        if field.is_required():
            parameters.append(
                inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, annotation=annotation)
            )
        else:
            parameters.append(
                inspect.Parameter(
                    name,
                    inspect.Parameter.KEYWORD_ONLY,
                    annotation=annotation,
                    default=field.get_default(call_default_factory=True),
                )
            )
    return inspect.Signature(parameters)


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
