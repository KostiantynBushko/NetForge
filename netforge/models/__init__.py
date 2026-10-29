"""The data model layer of NetForge.

Everything that crosses a boundary in NetForge is a Pydantic model: the
requests an operation accepts, the responses it returns, the metadata of an
execution, the risk level an operation is declared at and the capability
category it belongs to.

Importing from ``netforge.models`` is the supported way to reach them.
"""

from __future__ import annotations

from netforge.models.base import (
    NetForgeModel,
    RequestModel,
    ResponseModel,
    utcnow,
)
from netforge.models.capability import CapabilityCategory
from netforge.models.result import OperationMeta, OperationResult
from netforge.models.risk import RISK_LEVEL_ORDER, RiskLevel

__all__ = [
    "CapabilityCategory",
    "NetForgeModel",
    "OperationMeta",
    "OperationResult",
    "RISK_LEVEL_ORDER",
    "RequestModel",
    "ResponseModel",
    "RiskLevel",
    "utcnow",
]
