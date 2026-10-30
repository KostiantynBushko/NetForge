"""Execution results and metadata.

An operation's ``execute()`` returns its own typed response model.  When a
caller also wants to know *how* the operation ran -- how long it took, what
it warned about, which native implementation served it -- the result is
wrapped in an :class:`OperationResult`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import Field

from netforge.models.base import NetForgeModel
from netforge.models.risk import RiskLevel

__all__ = ["OperationMeta", "OperationResult", "ResultT"]

ResultT = TypeVar("ResultT")


class OperationMeta(NetForgeModel):
    """Metadata about a single execution of an operation."""

    operation: str = Field(description="The name of the operation that ran.")
    category: str = Field(description="The capability category of the operation.")
    risk_level: RiskLevel = Field(description="The risk level the operation was declared at.")
    started_at: datetime = Field(description="When the operation started.")
    finished_at: datetime = Field(description="When the operation finished.")
    duration_ms: float = Field(ge=0.0, description="Wall-clock duration in milliseconds.")
    implementation: str = Field(
        default="python",
        description="The implementation that served the operation (python, rust, c++).",
    )
    warnings: list[str] = Field(default_factory=list, description="Non-fatal remarks.")
    metadata: dict[str, str] = Field(default_factory=dict, description="Adapter-specific metadata.")


class OperationResult(NetForgeModel, Generic[ResultT]):
    """A typed response together with the metadata of the execution."""

    data: ResultT = Field(description="The operation's typed response.")
    meta: OperationMeta = Field(description="Metadata about the execution.")
