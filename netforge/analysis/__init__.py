"""The analysis capability.

Analysis reads what was captured and reports what it means: the flows, the
protocols, the sizes.  Everything in this package is read-only, so every
operation is declared at the safe risk level.
"""

from __future__ import annotations

from netforge.analysis.flow import (
    Flow,
    FlowAnalysisOperation,
    FlowAnalyzer,
    FlowAnalysisRequest,
    FlowAnalysisResponse,
    Packet,
    read_pcap,
)

__all__ = [
    "Flow",
    "FlowAnalysisOperation",
    "FlowAnalysisRequest",
    "FlowAnalysisResponse",
    "FlowAnalyzer",
    "Packet",
    "read_pcap",
]
