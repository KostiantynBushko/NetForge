"""Strongly typed request/response models.

Every NetForge capability speaks in Pydantic models.  The models are the
*contract* of an operation: they are what the registry publishes as a JSON
Schema, what the REST and MCP adapters validate against, and what the
LlamaIndex adapter turns into a function signature.

The base configuration is deliberately strict:

``extra="forbid"``
    A typo in a field name is an error, not a silently ignored key.  An
    operator who writes ``"timout"`` gets told about it instead of getting
    the default timeout and no idea why the command took the default path.

``validate_assignment=True``
    Mutating a request after validation re-validates it, so an operation can
    never receive a request that has drifted out of contract.

The configuration deliberately does **not** strip whitespace.  A request
that carries a configuration, a certificate or a script must reach the
operation byte for byte; stripping it would silently change what the
operator asked for.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "NetForgeModel",
    "RequestModel",
    "ResponseModel",
    "utcnow",
]


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class NetForgeModel(BaseModel):
    """Base class for every request and response exchanged with NetForge."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )

    def to_json_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the model."""
        return self.model_dump(mode="json")


class RequestModel(NetForgeModel):
    """Base class for operation requests."""


class ResponseModel(NetForgeModel):
    """Base class for operation responses.

    Responses carry a small amount of self-describing metadata so that an
    adapter can render them without knowing the concrete operation: the
    operation name, the risk level it ran at, and how long it took.
    """

    operation: str = Field(default="", description="Name of the operation that produced this response.")
    risk_level: str = Field(default="", description="Risk level the operation was declared at.")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Wall-clock duration of the operation.")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal remarks about the result.")
