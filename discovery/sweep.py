"""Ping sweeps.

A sweep is a ping against every address of a network, run concurrently.
The address expansion is done with :mod:`ipaddress`, so a CIDR, a range
and a bare address all work, and the sweep refuses a network that is larger
than the caller asked for -- a /8 is 16 million hosts, and nobody means to
type that by accident.
"""

from __future__ import annotations

import asyncio
import ipaddress
import time

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.discovery.ping import PingOperation, PingRequest
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["PingSweepOperation", "expand_network"]

_logger = get_logger("discovery.sweep")

#: The largest number of addresses a single sweep will touch.
MAX_HOSTS = 1024


def expand_network(specification: str, *, max_hosts: int = MAX_HOSTS) -> list[str]:
    """Expand ``specification`` into the list of addresses to probe.

    ``specification`` may be a CIDR block (``192.168.1.0/24``), a range
    (``192.168.1.10-192.168.1.20``) or a single address.  The network and
    the broadcast address of a CIDR block are excluded -- neither answers a
    ping on a normal network.
    """
    text = specification.strip()
    if not text:
        raise ValueError("the network specification is empty")

    if "/" in text:
        network = ipaddress.ip_network(text, strict=False)
        hosts = [str(host) for host in network.hosts()]
    elif "-" in text:
        start_text, _, end_text = text.partition("-")
        start = ipaddress.ip_address(start_text.strip())
        end = ipaddress.ip_address(end_text.strip())
        if int(end) < int(start):
            raise ValueError(f"the range {text!r} ends before it starts")
        hosts = [str(ipaddress.ip_address(value)) for value in range(int(start), int(end) + 1)]
    else:
        hosts = [str(ipaddress.ip_address(text))]

    if len(hosts) > max_hosts:
        raise ValueError(
            f"{specification!r} expands to {len(hosts)} addresses, which is more than the "
            f"limit of {max_hosts}. Narrow the network or raise max_hosts."
        )
    return hosts


class PingSweepRequest(RequestModel):
    """Request of :class:`PingSweepOperation`."""

    network: str = Field(description="The CIDR block, address range or single address to sweep.")
    concurrency: int = Field(default=32, ge=1, le=512, description="How many pings to run at once.")
    count: int = Field(default=1, ge=1, le=10, description="How many echo requests per host.")
    timeout: float | None = Field(default=3.0, gt=0.0, description="Per-packet timeout in seconds.")
    max_hosts: int = Field(default=MAX_HOSTS, ge=1, description="The largest network that may be swept.")


class PingSweepResponse(ResponseModel):
    """Response of :class:`PingSweepOperation`."""

    network: str
    scanned: int = 0
    alive: list[str] = Field(default_factory=list)
    unreachable: list[str] = Field(default_factory=list)
    details: list[dict[str, object]] = Field(default_factory=list)


class PingSweepOperation(Operation[PingSweepRequest, PingSweepResponse]):
    """Ping every address of a network and report the ones that answer."""

    name = "discovery.ping.sweep"
    category = CapabilityCategory.DISCOVERY
    risk_level = RiskLevel.OBSERVABILITY
    summary = "Ping every address of a network and report the hosts that answer."
    description = (
        "Expands a CIDR block, an address range or a single address and pings every host "
        "in it, concurrently. The addresses that answer are reported as the alive set. "
        "The sweep puts traffic on the network, which is why it is declared at the "
        "observability level rather than at the safe level."
    )
    tags = frozenset({"ping", "sweep", "cidr", "network"})

    request_model = PingSweepRequest
    response_model = PingSweepResponse

    async def execute(
        self, request: PingSweepRequest, context: ExecutionContext
    ) -> PingSweepResponse:
        """Sweep the network."""
        try:
            hosts = expand_network(request.network, max_hosts=request.max_hosts)
        except ValueError as exc:
            return PingSweepResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                network=request.network,
                scanned=0,
                alive=[],
                unreachable=[],
                details=[],
                warnings=[str(exc)],
            )
        semaphore = asyncio.Semaphore(request.concurrency)
        operation = PingOperation()

        async def probe(host: str) -> tuple[str, bool, float | None]:
            async with semaphore:
                response = await operation.run_request(
                    PingRequest(host=host, count=request.count, timeout=request.timeout),
                    context,
                )
                return host, response.reachable, response.avg_ms

        started = time.perf_counter()
        results = await asyncio.gather(*(probe(host) for host in hosts))

        alive = [host for host, reachable, _latency in results if reachable]
        unreachable = [host for host, reachable, _latency in results if not reachable]
        details = [
            {"host": host, "reachable": reachable, "avg_ms": latency}
            for host, reachable, latency in results
        ]

        return PingSweepResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            network=request.network,
            scanned=len(hosts),
            alive=alive,
            unreachable=unreachable,
            details=details,
        )
