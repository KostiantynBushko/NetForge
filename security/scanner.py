"""TCP port scanning.

The scanner opens a TCP connection to each port and records whether it was
accepted and how long the accept took.  A closed port is refused
immediately and a filtered port is dropped, and the difference between the
two is exactly what the scan tells you.

The scan is concurrent, with a bounded number of connections, and the port
list can be given as ranges.  The service names come from the system's own
services database.
"""

from __future__ import annotations

import asyncio
import socket
import time
from dataclasses import dataclass

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = [
    "PortScanRequest",
    "PortScanResponse",
    "PortScannerOperation",
    "expand_ports",
    "scan_port",
]

_logger = get_logger("security.scanner")


@dataclass(slots=True)
class ScanResult:
    """The outcome of scanning one port."""

    port: int
    state: str  # "open", "closed" or "filtered"
    latency_ms: float | None = None
    service: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the result as a plain dictionary."""
        return {
            "port": self.port,
            "state": self.state,
            "latency_ms": round(self.latency_ms, 3) if self.latency_ms is not None else None,
            "service": self.service,
        }


def expand_ports(specification: str | list[int]) -> list[int]:
    """Expand a port specification into a list of port numbers.

    The specification may be a list of numbers, or a comma-separated string
    of numbers and ranges: ``"22,80,443,8000-8100"``.
    """
    if isinstance(specification, list):
        return [int(port) for port in specification]

    ports: list[int] = []
    for part in specification.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, _, end_text = part.partition("-")
            start, end = int(start_text), int(end_text)
            if end < start:
                raise ValueError(f"the range {part!r} ends before it starts")
            ports.extend(range(start, end + 1))
        else:
            ports.append(int(part))
    return ports


def _service_name(port: int) -> str | None:
    try:
        return socket.getservbyport(port, "tcp")
    except OSError:
        return None


async def scan_port(host: str, port: int, *, timeout: float = 2.0) -> ScanResult:
    """Scan a single TCP port."""
    started = time.perf_counter()
    writer: asyncio.StreamWriter | None = None
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except ConnectionRefusedError:
        return ScanResult(port=port, state="closed", service=_service_name(port))
    except asyncio.TimeoutError:
        return ScanResult(port=port, state="filtered", service=_service_name(port))
    except OSError:
        return ScanResult(port=port, state="filtered", service=_service_name(port))

    latency = (time.perf_counter() - started) * 1000.0
    if writer is not None:
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, asyncio.TimeoutError):  # pragma: no cover - best effort
            pass
    return ScanResult(port=port, state="open", latency_ms=latency, service=_service_name(port))


class PortScanRequest(RequestModel):
    """Request of :class:`PortScannerOperation`."""

    host: str = Field(min_length=1, description="The host to scan.")
    ports: list[int] | str = Field(
        default_factory=lambda: [22, 80, 443],
        description="The ports to scan. A list of numbers, or a string of numbers and ranges.",
    )
    timeout: float | None = Field(default=2.0, gt=0.0, description="Connect timeout per port.")
    concurrency: int = Field(default=64, ge=1, le=1024, description="How many ports to probe at once.")


class PortScanResponse(ResponseModel):
    """Response of :class:`PortScannerOperation`."""

    host: str
    results: list[dict[str, object]] = Field(default_factory=list)
    open_ports: list[int] = Field(default_factory=list)
    closed_ports: list[int] = Field(default_factory=list)
    filtered_ports: list[int] = Field(default_factory=list)
    scanned: int = 0
    duration_ms: float = 0.0


class PortScannerOperation(Operation[PortScanRequest, PortScanResponse]):
    """Scan the TCP ports of a host."""

    name = "security.portscan"
    category = CapabilityCategory.SECURITY
    risk_level = RiskLevel.OBSERVABILITY
    summary = "Scan the TCP ports of a host and report which of them are open."
    description = (
        "Probes the TCP ports of a host and reports each one as open, closed or "
        "filtered. The scan opens and closes a connection per port, which the target "
        "can observe, so the operation is declared at the observability level rather "
        "than at the safe level."
    )
    tags = frozenset({"scan", "ports", "tcp", "security"})

    request_model = PortScanRequest
    response_model = PortScanResponse

    async def execute(
        self, request: PortScanRequest, context: ExecutionContext
    ) -> PortScanResponse:
        """Scan the ports."""
        try:
            ports = expand_ports(request.ports)
        except (TypeError, ValueError) as exc:
            return PortScanResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                host=request.host,
                results=[],
                scanned=0,
                warnings=[f"the port specification could not be read: {exc}"],
            )

        semaphore = asyncio.Semaphore(request.concurrency)
        timeout = request.timeout or 2.0

        async def probe(port: int) -> ScanResult:
            async with semaphore:
                return await scan_port(request.host, port, timeout=timeout)

        started = time.perf_counter()
        results = await asyncio.gather(*(probe(port) for port in ports))
        elapsed = (time.perf_counter() - started) * 1000.0

        ordered = sorted(results, key=lambda result: result.port)
        return PortScanResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=elapsed,
            host=request.host,
            results=[result.to_dict() for result in ordered],
            open_ports=[result.port for result in ordered if result.state == "open"],
            closed_ports=[result.port for result in ordered if result.state == "closed"],
            filtered_ports=[result.port for result in ordered if result.state == "filtered"],
            scanned=len(ordered),
        )
