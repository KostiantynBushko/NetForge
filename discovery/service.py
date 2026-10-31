"""Service discovery.

Service discovery is the combination of a port probe and an identification:
which ports are open, and what is listening on them.

The service names come from the system's own database (``/etc/services``
through :mod:`socket`), so the answer is the one the machine itself would
give, and not a table hard-coded in NetForge.
"""

from __future__ import annotations

import asyncio
import shlex
import socket
import time

from pydantic import Field, model_validator

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.core.runner import which
from netforge.discovery import nmap
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel
from netforge.models.scanning import Aggressiveness, ScanEngine, the_profile

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
    timeout: float | None = Field(
        default=None,
        gt=0.0,
        description="Connect timeout per port. The level decides when it is not given.",
    )
    concurrency: int | None = Field(
        default=None,
        ge=1,
        le=256,
        description="How many probes to run at once. The level decides when it is not given.",
    )
    engine: ScanEngine = Field(
        default=ScanEngine.NATIVE,
        description="The scanner that runs the scan: the native one, or nmap.",
    )
    aggressiveness: Aggressiveness = Field(
        default=Aggressiveness.NORMAL,
        description="How hard the scan pushes, and how visible it is on the target.",
    )
    nmap_command: str | None = Field(
        default=None,
        description=(
            "An nmap command line to run instead of the one NetForge builds. "
            "It must run nmap, and it must scan the host of the request."
        ),
    )

    @model_validator(mode="after")
    def _the_command_is_sane(self) -> ServiceDiscoveryRequest:
        """Check a command that was written by hand.

        The check is here, and not in the operation, so that every
        adapter refuses the same command the same way -- and refuses it
        before anything is run.
        """
        if self.nmap_command is None:
            return self

        if "engine" in self.model_fields_set and self.engine is ScanEngine.NATIVE:
            raise ValueError(
                "the nmap command needs the nmap engine, but the engine was "
                "set to the native scanner"
            )
        if self.engine is ScanEngine.NATIVE:
            # The command says which engine to run, and the caller did
            # not say otherwise.
            self.engine = ScanEngine.NMAP

        nmap.the_custom_arguments(self.nmap_command, self.host)
        return self


class ServiceDiscoveryResponse(ResponseModel):
    """Response of :class:`ServiceDiscoveryOperation`."""

    host: str = Field(description="The host that was probed.")
    open_ports: list[dict[str, object]] = Field(default_factory=list, description="The ports that were open, and the services on them.")
    closed_ports: list[int] = Field(default_factory=list, description="The ports that were closed.")
    scanned: int = Field(default=0, description="How many ports were probed.")
    engine: str = Field(default="native", description="The scanner that ran the scan.")
    aggressiveness: str = Field(
        default="normal", description="The level the scan was run at."
    )
    command: str | None = Field(
        default=None, description="The command that was run, when one was."
    )


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
        "operation is declared at the observability level. The nmap engine can also be "
        "given a command of the caller's own; such a command can do anything nmap can "
        "do, and is held to the system modification level until the caller allows it."
    )
    tags = frozenset({"service", "ports", "enumeration"})

    request_model = ServiceDiscoveryRequest
    response_model = ServiceDiscoveryResponse

    async def execute(
        self, request: ServiceDiscoveryRequest, context: ExecutionContext
    ) -> ServiceDiscoveryResponse:
        """Probe the ports."""
        if request.nmap_command is not None:
            # A command that was written by hand can do anything nmap can
            # do: run a script, write a file, reach a whole network.  It
            # is not the risk of this operation any more, so it is held
            # to the highest level until the caller allows it.
            context.check_risk(self.name, RiskLevel.SYSTEM_MODIFICATION)

        if request.engine is ScanEngine.NMAP:
            return await self._with_nmap(request, context)
        return await self._with_the_native_scanner(request, context)

    async def _with_the_native_scanner(
        self, request: ServiceDiscoveryRequest, context: ExecutionContext
    ) -> ServiceDiscoveryResponse:
        """Probe the ports with the scanner of NetForge itself."""
        ports = request.ports or list(COMMON_PORTS)
        profile = the_profile(request.aggressiveness)
        timeout = profile.the_timeout(request.timeout or 2.0)
        concurrency = profile.the_concurrency(request.concurrency or 32)
        semaphore = asyncio.Semaphore(concurrency)

        async def probe(port: int) -> tuple[int, bool, float | None]:
            started = time.perf_counter()
            async with semaphore:
                if profile.delay:
                    # The level asked for a pause between the probes.
                    await asyncio.sleep(profile.delay)
                writer: asyncio.StreamWriter | None = None
                try:
                    _reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(request.host, port),
                        timeout=timeout,
                    )
                except (TimeoutError, OSError):
                    return port, False, None
                elapsed = (time.perf_counter() - started) * 1000.0
                writer.close()
                try:
                    await writer.wait_closed()
                except (TimeoutError, OSError):  # pragma: no cover - best effort
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
            engine=request.engine.value,
            aggressiveness=request.aggressiveness.value,
        )

    async def _with_nmap(
        self, request: ServiceDiscoveryRequest, context: ExecutionContext
    ) -> ServiceDiscoveryResponse:
        """Probe the ports with nmap."""
        started = time.perf_counter()
        ports = request.ports or list(COMMON_PORTS)
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
            # The engine that ran is the native one, whatever was asked
            # for: the answer must not name an engine that did not run.
            response.engine = ScanEngine.NATIVE.value
            response.aggressiveness = request.aggressiveness.value
            return response

        if request.nmap_command is not None:
            arguments, remarks = nmap.the_custom_arguments(request.nmap_command, request.host)
            warnings.extend(remarks)
        else:
            arguments = nmap.the_arguments(
                host=request.host,
                ports=",".join(str(port) for port in ports),
                level=request.aggressiveness,
                timeout=timeout,
                root=root,
            )
        # The command is rendered here, and not read back from the
        # runner, so that the answer names the command that was asked
        # for whatever the runner is.
        command = shlex.join(arguments)
        result = await context.runner().run(arguments, timeout=context.timeout)
        if not result.ok:
            detail = (result.stderr or result.stdout).strip()
            return ServiceDiscoveryResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                host=request.host,
                open_ports=[],
                closed_ports=[],
                scanned=0,
                engine=request.engine.value,
                aggressiveness=request.aggressiveness.value,
                command=command,
                warnings=[f"nmap exited with the status {result.returncode}: {detail}"],
            )

        try:
            found = nmap.parse_nmap_xml(result.stdout)
        except ValueError as exc:
            return ServiceDiscoveryResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                host=request.host,
                open_ports=[],
                closed_ports=[],
                scanned=0,
                engine=request.engine.value,
                aggressiveness=request.aggressiveness.value,
                command=command,
                warnings=[str(exc)],
            )

        warnings.extend(found.warnings)
        return ServiceDiscoveryResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            host=request.host,
            open_ports=found.the_open(),
            closed_ports=found.closed_ports,
            scanned=found.scanned,
            engine=request.engine.value,
            aggressiveness=request.aggressiveness.value,
            command=command,
            warnings=warnings,
        )
