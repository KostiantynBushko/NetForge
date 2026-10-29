"""Traceroute.

Like ping, traceroute shells out to the system tool.  The output parser
handles the Linux and the BSD shapes, which differ in the separator between
the hops and in the way the address is annotated.
"""

from __future__ import annotations

import re
import time

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["TracerouteOperation", "parse_traceroute_output"]

_logger = get_logger("discovery.traceroute")

_HOP_RE = re.compile(
    r"^\s*(?P<hop>\d+)\s+(?P<rest>.+?)\s*$",
)
_ADDRESS_RE = re.compile(r"(?P<address>[0-9a-fA-F:.]+)")
_RTT_RE = re.compile(r"(?P<rtt>[\d.]+)\s*ms")


def parse_traceroute_output(output: str) -> list[dict[str, object]]:
    """Parse the output of a ``traceroute`` run into a list of hops.

    Each hop is a dictionary with the hop number, the address (when the hop
    answered), the round-trip times and whether the hop timed out.
    """
    hops: list[dict[str, object]] = []
    for line in (output or "").splitlines():
        line = line.strip()
        if not line:
            continue
        match = _HOP_RE.match(line)
        if not match:
            continue
        hop_number = int(match.group("hop"))
        rest = match.group("rest")

        if rest.startswith("*") or "no reply" in rest.lower():
            hops.append({"hop": hop_number, "address": None, "rtts_ms": [], "timeout": True})
            continue

        address_match = _ADDRESS_RE.search(rest)
        address = address_match.group("address") if address_match else None
        rtts = [float(value) for value in _RTT_RE.findall(rest)]
        hops.append(
            {
                "hop": hop_number,
                "address": address,
                "rtts_ms": rtts,
                "timeout": not rtts,
            }
        )
    return hops


class TracerouteRequest(RequestModel):
    """Request of :class:`TracerouteOperation`."""

    host: str = Field(min_length=1, description="The host to trace the route to.")
    max_hops: int = Field(default=30, ge=1, le=64, description="The maximum number of hops.")
    timeout: float | None = Field(default=5.0, gt=0.0, description="Per-probe timeout in seconds.")


class TracerouteResponse(ResponseModel):
    """Response of :class:`TracerouteOperation`."""

    host: str
    hops: list[dict[str, object]] = Field(default_factory=list)
    reached: bool = False


class TracerouteOperation(Operation[TracerouteRequest, TracerouteResponse]):
    """Trace the network path to a host."""

    name = "discovery.traceroute"
    category = CapabilityCategory.DISCOVERY
    risk_level = RiskLevel.SAFE
    summary = "Trace the network path to a host and report every hop."
    description = (
        "Runs traceroute towards a host and reports each hop, the address it answered "
        "from and the round-trip times. The trace is read-only observation of the path, "
        "so the operation is declared at the safe level."
    )
    tags = frozenset({"traceroute", "route", "path", "latency"})

    request_model = TracerouteRequest
    response_model = TracerouteResponse

    async def execute(
        self, request: TracerouteRequest, context: ExecutionContext
    ) -> TracerouteResponse:
        """Run the traceroute and parse its output."""
        runner = context.runner()
        argv = [
            "traceroute",
            "-m",
            str(request.max_hops),
            "-w",
            str(max(1, int(request.timeout or 5))),
            request.host,
        ]
        started = time.perf_counter()
        try:
            result = await runner.run(argv, timeout=context.timeout)
            output = f"{result.stdout}\n{result.stderr}"
        except Exception as exc:
            return TracerouteResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                host=request.host,
                hops=[],
                warnings=[f"traceroute could not be run: {exc}"],
            )

        hops = parse_traceroute_output(output)
        reached = bool(hops) and not hops[-1].get("timeout", True)
        return TracerouteResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            host=request.host,
            hops=hops,
            reached=reached,
        )
