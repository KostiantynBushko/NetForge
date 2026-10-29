"""The description of a registered operation.

A descriptor is the *published* form of an operation: everything an adapter
needs to present it, and nothing that requires importing the implementation.
The REST adapter serves descriptors as JSON, the MCP adapter turns them into
tool descriptions, and the CLI adapter renders them as a table.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from netforge.models.base import NetForgeModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["OperationDescriptor"]


class OperationDescriptor(NetForgeModel):
    """The published metadata of one operation."""

    name: str = Field(description="The name the operation is published under.")
    category: CapabilityCategory = Field(description="The capability category.")
    risk_level: RiskLevel = Field(description="The declared risk level.")
    summary: str = Field(default="", description="One-line summary.")
    description: str = Field(default="", description="The full description.")
    tags: list[str] = Field(default_factory=list, description="Free-form tags.")
    aliases: list[str] = Field(default_factory=list, description="Alternative names.")
    requires_privilege: bool = Field(default=False, description="Whether elevated privileges are needed.")
    request_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema of the request.")
    response_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema of the response.")
    implementation: str = Field(default="module:Operation", description="Import path of the implementation.")
