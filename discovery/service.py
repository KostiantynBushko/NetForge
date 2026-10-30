"""Service discovery.

Service discovery is the combination of a port probe and an identification:
which ports are open, and what is listening on them.

The service names come from the system's own database (``/etc/services``
through :mod:`socket`), so the answer is the one the machine itself would
give, and not a table hard-coded in NetForge.
"""

from __future__ import annotations

import asyncio
import socket
import time

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["ServiceDiscoveryOperation", "lookup_service_name", "COMMON_PORTS"]

_logger = get_logger("discovery.service")

#: A small set of ports that is worth checking when nobody says otherwise.
COMMON_PORTS: tuple[int, ...] = (21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 5432, 8080, 8443)


def lookup_service_name(port: int, protocol: str = "tcp") -> str | None:
    """Return the service name for ``port``, or ``None`` when it is unknown."""
    try:
        return socket.getservbyport(port, protocol)
    except OSError:
        return None


class ServiceDiscoveryRequest(RequestModel):
    """Request of :class:`ServiceDiscoveryOperation`."""

    host: str = Field(description="The host to inspect.")
    ports: list[int] = Field(
        default_factory=lambda: list(COMMON_PORTS),
        description="The ports to probe. An empty list uses the common set.",
    )
    timeout: float | None = Field(default=2.0, gt=0.0, description="Connect timeout per port.")
    concurrency: int = Field(default=32, ge=1, le=256, description="How many probes to run at once.")


class ServiceDiscoveryResponse(ResponseModel):
    """Response of :class:`ServiceDiscoveryOperation`."""

    host: str
    open_ports: list[dict[str, object]] = Field(default_factory=list)
    closed_ports: list[int] = Field(default_factory=list)
    scanned: int = 0


class ServiceDiscoveryOperation(Operation[ServiceDiscoveryRequest, ServiceDiscoveryResponse]):
    """Find the open ports of a host and name the services on them."""

    name = "discovery.service.enumerate"
    category = CapabilityCategory.DISCOVERY
    risk_level = RiskLevel.OBSERVABILITY
    summary = "Probe the ports of a host and name the services that are listening."
    description = (
        "Probes a set of TCP ports on a host and reports which of them are open, together "
        "with the service name from the system's own services database. The probe opens "
        "and closes a connection per port, which is observable on the wire, so the "
        "operation is declared at the observability level."
    )
    tags = frozenset({"service", "ports", "enumeration"})

    request_model = ServiceDiscoveryRequest
    response_model = ServiceDiscoveryResponse

    async def execute(
        self, request: ServiceDiscoveryRequest, context: ExecutionContext
    ) -> ServiceDiscoveryResponse:
        """Probe the ports."""
        ports = request.ports or list(COMMON_PORTS)
        semaphore = asyncio.Semaphore(request.concurrency)

        async def probe(port: int) -> tuple[int, bool, float | None]:
            started = time.perf_counter()
            async with semaphore:
                writer: asyncio.StreamWriter | None = None
                try:
                    _reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(request.host, port),
                        timeout=request.timeout or 2.0,
                    )
                except (OSError, asyncio.TimeoutError):
                    return port, False, None
                elapsed = (time.perf_counter() - started) * 1000.0
                writer.close()
                try:
                    await writer.wait_closed()
                except (OSError, asyncio.TimeoutError):  # pragma: no cover - best effort
                    pass
                return port, True, elapsed

        started = time.perf_counter()
        results = await asyncio.gather(*(probe(port) for port in ports))

        open_ports: list[dict[str, object]] = []
        closed_ports: list[int] = []
        for port, is_open, latency in sorted(results):
            if is_open:
                open_ports.append(
                    {
                        "port": port,
                        "service": lookup_service_name(port),
                        "latency_ms": latency,
                    }
                )
            else:
                closed_ports.append(port)

        return ServiceDiscoveryResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            host=request.host,
            open_ports=open_ports,
            closed_ports=closed_ports,
            scanned=len(ports),
        )
