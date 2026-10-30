"""The operation contract.

An *operation* is the unit NetForge exposes.  It is a class -- not a
function -- because an operation carries identity: a name, a capability
category, a risk level, a request schema and a response schema.  That
identity is what the registry publishes and what every adapter renders.

Three properties are enforced by the framework rather than by convention:

**Async first.**  ``execute()`` is a coroutine.  Even an operation that does
nothing but read a file is awaited, so the calling code does not have to
change shape when an operation becomes slow.

**Strongly typed.**  An operation declares its request and response models.
The registry publishes them as JSON Schema, and the REST, MCP and LlamaIndex
adapters derive their own contracts from them.

**A declared risk level.**  Every operation states its risk level at class
definition time.  :meth:`Operation.__init_subclass__` refuses to create a
concrete operation that has not, so "the risk level is missing" cannot
reach production.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Generic, TypeVar

from netforge.core.context import ExecutionContext
from netforge.core.exceptions import OperationExecutionError
from netforge.models.base import RequestModel, ResponseModel, utcnow
from netforge.models.capability import CapabilityCategory
from netforge.models.result import OperationMeta, OperationResult
from netforge.models.risk import RiskLevel

__all__ = ["Operation", "RequestT", "ResponseT"]

RequestT = TypeVar("RequestT", bound=RequestModel)
ResponseT = TypeVar("ResponseT", bound=ResponseModel)


class Operation(ABC, Generic[RequestT, ResponseT]):
    """Base class of every NetForge operation."""

    #: The name the operation is published under.  Must be unique.
    name: ClassVar[str] = ""

    #: The capability category the operation belongs to.
    category: ClassVar[CapabilityCategory] = CapabilityCategory.CONNECTIVITY

    #: The risk level the operation is declared at.
    risk_level: ClassVar[RiskLevel] = RiskLevel.SAFE

    #: A one-line summary, shown in menus and tool listings.
    summary: ClassVar[str] = ""

    #: The longer description, shown by ``netforge describe``.
    description: ClassVar[str] = ""

    #: Free-form tags, used by the registry's filters.
    tags: ClassVar[frozenset[str]] = frozenset()

    #: The model the request is validated against.
    request_model: ClassVar[type[RequestModel]]

    #: The model the response is validated against.
    response_model: ClassVar[type[ResponseModel]]

    #: Whether the operation needs elevated privileges to work.
    requires_privilege: ClassVar[bool] = False

    #: Whether a native (Rust/C++) implementation may serve this operation.
    supports_native: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        # An intermediate abstract class is allowed to be incomplete; a
        # concrete one is not.
        execute = cls.__dict__.get("execute")
        if execute is None:
            return
        if getattr(execute, "__isabstractmethod__", False):
            return

        missing: list[str] = []
        if not cls.__dict__.get("name"):
            missing.append("name")
        if not cls.__dict__.get("category"):
            missing.append("category")
        if not cls.__dict__.get("risk_level"):
            missing.append("risk_level")
        if "request_model" not in cls.__dict__:
            missing.append("request_model")
        if "response_model" not in cls.__dict__:
            missing.append("response_model")
        if missing:
            raise TypeError(
                f"{cls.__name__} is a concrete operation but does not declare: "
                f"{', '.join(missing)}. Every NetForge operation must declare its "
                f"name, category, risk level and its request and response models."
            )

    # -- execution ----------------------------------------------------------

    @abstractmethod
    async def execute(self, request: RequestT, context: ExecutionContext) -> ResponseT:
        """Perform the operation.

        Subclasses implement this.  The framework has already validated the
        request and checked the risk level by the time this is called.
        """

    async def run(self, context: ExecutionContext | None = None, **kwargs: Any) -> ResponseT:
        """Validate ``kwargs`` into a request and execute the operation."""
        context = context or ExecutionContext()
        # The risk check comes first: an operation that is above the ceiling
        # is refused whatever its payload says.
        context.check_risk(self.name, self.risk_level)
        request = self.request_model(**kwargs)
        return await self.execute(request, context)

    async def run_request(
        self,
        request: RequestT | dict[str, Any],
        context: ExecutionContext | None = None,
    ) -> ResponseT:
        """Execute the operation with an already-built request."""
        context = context or ExecutionContext()
        context.check_risk(self.name, self.risk_level)
        if isinstance(request, dict):
            request = self.request_model.model_validate(request)
        return await self.execute(request, context)

    async def run_with_meta(
        self,
        request: RequestT | dict[str, Any],
        context: ExecutionContext | None = None,
    ) -> OperationResult[ResponseT]:
        """Execute the operation and return the result with its metadata."""
        context = context or ExecutionContext()
        started = utcnow()
        clock = time.perf_counter()
        data = await self.run_request(request, context)
        duration_ms = (time.perf_counter() - clock) * 1000.0
        meta = OperationMeta(
            operation=self.name,
            category=self.category.value,
            risk_level=self.risk_level,
            started_at=started,
            finished_at=utcnow(),
            duration_ms=duration_ms,
        )
        return OperationResult(data=data, meta=meta)

    # -- description --------------------------------------------------------

    @classmethod
    def describe(cls) -> dict[str, Any]:
        """Return a JSON-serialisable description of the operation."""
        return {
            "name": cls.name,
            "category": cls.category.value,
            "risk_level": int(cls.risk_level),
            "risk_label": cls.risk_level.label,
            "summary": cls.summary or (cls.__doc__ or "").strip().splitlines()[0]
            if (cls.summary or cls.__doc__)
            else "",
            "description": cls.description or (cls.__doc__ or "").strip(),
            "tags": sorted(cls.tags),
            "requires_privilege": cls.requires_privilege,
            "request_schema": cls.request_model.model_json_schema(),
            "response_schema": cls.response_model.model_json_schema(),
        }

    @classmethod
    def require(cls, condition: bool, message: str) -> None:
        """Raise :class:`OperationExecutionError` when ``condition`` is false."""
        if not condition:
            raise OperationExecutionError(message)
