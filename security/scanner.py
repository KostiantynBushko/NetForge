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
from netforge.core.runner import which
from netforge.discovery import nmap
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel
from netforge.models.scanning import Aggressiveness, ScanEngine, the_profile

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
            "version": None,
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
    timeout: float | None = Field(
        default=None,
        gt=0.0,
        description="Connect timeout per port. The level decides when it is not given.",
    )
    concurrency: int | None = Field(
        default=None,
        ge=1,
        le=1024,
        description="How many ports to probe at once. The level decides when it is not given.",
    )
    engine: ScanEngine = Field(
        default=ScanEngine.NATIVE,
        description="The scanner that runs the scan: the native one, or nmap.",
    )
    aggressiveness: Aggressiveness = Field(
        default=Aggressiveness.NORMAL,
        description="How hard the scan pushes, and how visible it is on the target.",
    )


class PortScanResponse(ResponseModel):
    """Response of :class:`PortScannerOperation`."""

    host: str = Field(description="The host that was scanned.")
    results: list[dict[str, object]] = Field(default_factory=list, description="The result of every port that was scanned.")
    open_ports: list[int] = Field(default_factory=list, description="The ports that were open.")
    closed_ports: list[int] = Field(default_factory=list, description="The ports that were closed.")
    filtered_ports: list[int] = Field(default_factory=list, description="The ports that were filtered.")
    scanned: int = Field(default=0, description="How many ports were scanned.")
    duration_ms: float = Field(default=0.0, description="How long the scan took, in milliseconds.")
    engine: str = Field(default="native", description="The scanner that ran the scan.")
    aggressiveness: str = Field(
        default="normal", description="The level the scan was run at."
    )


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
        if request.engine is ScanEngine.NMAP:
            return await self._with_nmap(request, context)
        return await self._with_the_native_scanner(request, context)

    async def _with_the_native_scanner(
        self, request: PortScanRequest, context: ExecutionContext
    ) -> PortScanResponse:
        """Scan the ports with the scanner of NetForge itself."""
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

        profile = the_profile(request.aggressiveness)
        timeout = profile.the_timeout(request.timeout or 2.0)
        concurrency = profile.the_concurrency(request.concurrency or 64)
        semaphore = asyncio.Semaphore(concurrency)

        async def probe(port: int) -> ScanResult:
            async with semaphore:
                if profile.delay:
                    # The level asked for a pause between the probes.
                    await asyncio.sleep(profile.delay)
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
            engine=request.engine.value,
            aggressiveness=request.aggressiveness.value,
        )

    async def _with_nmap(
        self, request: PortScanRequest, context: ExecutionContext
    ) -> PortScanResponse:
        """Scan the ports with nmap."""
        started = time.perf_counter()
        profile = the_profile(request.aggressiveness)
        timeout = profile.the_timeout(request.timeout or 2.0)
        root = nmap.is_root()
        warnings = list(nmap.the_warnings(request.aggressiveness, root))

        if which("nmap") is None:
            # nmap was asked for and is not there: the native scanner
            # does the work, and the response says so.
            response = await self._with_the_native_scanner(request, context)
            response.warnings.append(
                "nmap is not installed; the native scanner was used instead"
            )
            response.engine = request.engine.value
            response.aggressiveness = request.aggressiveness.value
            return response

        specification = (
            request.ports
            if isinstance(request.ports, str)
            else ",".join(str(port) for port in request.ports)
        )
        arguments = nmap.the_arguments(
            host=request.host,
            ports=specification,
            level=request.aggressiveness,
            timeout=timeout,
            root=root,
        )
        result = await context.runner().run(arguments, timeout=context.timeout)
        if not result.ok:
            detail = (result.stderr or result.stdout).strip()
            return PortScanResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                host=request.host,
                results=[],
                scanned=0,
                engine=request.engine.value,
                aggressiveness=request.aggressiveness.value,
                warnings=[f"nmap exited with the status {result.returncode}: {detail}"],
            )

        try:
            found = nmap.parse_nmap_xml(result.stdout)
        except ValueError as exc:
            return PortScanResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                host=request.host,
                results=[],
                scanned=0,
                engine=request.engine.value,
                aggressiveness=request.aggressiveness.value,
                warnings=[str(exc)],
            )

        warnings.extend(found.warnings)
        return PortScanResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            host=request.host,
            results=found.ports,
            open_ports=found.open_ports,
            closed_ports=found.closed_ports,
            filtered_ports=found.filtered_ports,
            scanned=found.scanned,
            engine=request.engine.value,
            aggressiveness=request.aggressiveness.value,
            warnings=warnings,
        )
