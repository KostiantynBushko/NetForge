"""Traffic capture.

A capture session runs ``tcpdump`` (or ``dumpcap``) and writes a libpcap
file.  The filter is a BPF expression, and the filter *builder* -- which
produces one -- is implemented here as a pure function over a small model,
so a filter can be built, inspected and tested without a capture running.

The session itself is the one part that needs the system tool.  It is
started as a subprocess, and it is stopped by sending ``SIGINT``, which is
how ``tcpdump`` is asked to flush its buffer and close the file cleanly.
"""

from __future__ import annotations

import asyncio
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["BpfFilter", "CaptureSession", "CaptureOperation", "CaptureFilterRequest"]

_logger = get_logger("capture.session")


@dataclass(frozen=True, slots=True)
class BpfFilter:
    """A BPF capture filter.

    The class builds the expression; it does not evaluate it.  The parts
    are kept separate so the expression can be read back and checked.
    """

    host: str | None = None
    port: int | None = None
    protocol: str | None = None
    source: str | None = None
    destination: str | None = None
    direction: str | None = None
    extra: str | None = None
    parts: list[str] = field(default_factory=list)

    def to_expression(self) -> str:
        """Return the BPF expression."""
        terms: list[str] = []
        if self.protocol:
            terms.append(self.protocol)
        if self.host:
            terms.append(f"host {self.host}")
        if self.source:
            terms.append(f"src {self.source}")
        if self.destination:
            terms.append(f"dst {self.destination}")
        if self.port:
            terms.append(f"port {self.port}")
        if self.direction in {"inbound", "in"}:
            terms.append("inbound")
        elif self.direction in {"outbound", "out"}:
            terms.append("outbound")
        for part in self.parts:
            terms.append(part)
        if self.extra:
            terms.append(f"({self.extra})")
        return " and ".join(terms)

    def __str__(self) -> str:
        return self.to_expression()


class CaptureSession:
    """A running capture session."""

    def __init__(
        self,
        interface: str,
        output: Path,
        *,
        filter_expression: str | None = None,
        snaplen: int = 65535,
        command: str = "tcpdump",
        timeout: float | None = 30.0,
    ) -> None:
        self.interface = interface
        self.output = Path(output)
        self.filter_expression = filter_expression
        self.snaplen = snaplen
        self.command = command
        self.timeout = timeout
        self.process: asyncio.subprocess.Process | None = None
        self.started_at: float | None = None
        self.stderr_task: asyncio.Task[None] | None = None
        self.stderr_lines: list[str] = []

    def build_argv(self) -> list[str]:
        """Return the command line of the capture."""
        argv = [
            self.command,
            "-i",
            self.interface,
            "-w",
            str(self.output),
            "-s",
            str(self.snaplen),
        ]
        if self.filter_expression:
            argv.append(self.filter_expression)
        return argv

    async def start(self) -> None:
        """Start the capture."""
        self.output.parent.mkdir(parents=True, exist_ok=True)
        argv = self.build_argv()
        self.process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self.started_at = time.perf_counter()
        self.stderr_task = asyncio.create_task(self._drain_stderr())

    async def _drain_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        while True:
            line = await self.process.stderr.readline()
            if not line:
                break
            self.stderr_lines.append(line.decode("utf-8", errors="replace").rstrip())

    async def stop(self) -> int:
        """Stop the capture and return the exit code of the capture tool."""
        if self.process is None:
            return 0
        # tcpdump flushes its buffer and closes the file when it is
        # interrupted; killing it would truncate the capture.
        self.process.send_signal(signal.SIGINT)
        try:
            return_code = await asyncio.wait_for(self.process.wait(), timeout=10.0)
        except TimeoutError:  # pragma: no cover - the tool ignored the signal
            self.process.kill()
            return_code = await self.process.wait()
        if self.stderr_task is not None:
            self.stderr_task.cancel()
        return return_code or 0

    @property
    def elapsed_seconds(self) -> float:
        """Return how long the capture has been running."""
        if self.started_at is None:
            return 0.0
        return time.perf_counter() - self.started_at


class CaptureFilterRequest(RequestModel):
    """Request of :class:`CaptureOperation`."""

    interface: str = Field(default="any", description="The interface to capture on.")
    output: str = Field(description="The path of the capture file to write.")
    duration: float = Field(default=10.0, gt=0.0, le=3600.0, description="How long to capture for.")
    protocol: str | None = Field(default=None, description="Filter by protocol, e.g. 'tcp'.")
    host: str | None = Field(default=None, description="Filter by host.")
    port: int | None = Field(default=None, ge=1, le=65535, description="Filter by port.")
    source: str | None = Field(default=None, description="Filter by source address.")
    destination: str | None = Field(default=None, description="Filter by destination address.")
    direction: str | None = Field(default=None, description="Filter by direction: inbound or outbound.")
    expression: str | None = Field(default=None, description="A raw BPF expression to use as-is.")
    snaplen: int = Field(default=65535, ge=64, le=262144, description="How many bytes of each packet to keep.")


class CaptureResponse(ResponseModel):
    """Response of :class:`CaptureOperation`."""

    output: str = Field(description="The path of the capture file that was written.")
    interface: str = Field(description="The interface the packets were captured from.")
    expression: str = Field(default="", description="The filter the capture was filtered by.")
    duration_seconds: float = Field(default=0.0, description="How long the capture ran, in seconds.")
    bytes_written: int = Field(default=0, description="How many bytes were written to the capture file.")
    packets: int | None = Field(default=None, description="How many packets were captured.")


class CaptureOperation(Operation[CaptureFilterRequest, CaptureResponse]):
    """Capture packets from an interface into a libpcap file."""

    name = "capture.session"
    category = CapabilityCategory.CAPTURE
    risk_level = RiskLevel.OBSERVABILITY
    summary = "Capture packets from an interface into a libpcap file."
    description = (
        "Runs a packet capture on an interface for a fixed duration and writes the "
        "result to a libpcap file. The capture observes traffic without changing it, "
        "which is why the operation is declared at the observability level. It needs "
        "the privilege to open a raw socket."
    )
    tags = frozenset({"capture", "pcap", "tcpdump", "traffic"})
    requires_privilege = True

    request_model = CaptureFilterRequest
    response_model = CaptureResponse

    async def execute(
        self, request: CaptureFilterRequest, context: ExecutionContext
    ) -> CaptureResponse:
        """Run the capture."""
        if request.expression:
            expression = request.expression
        else:
            expression = BpfFilter(
                host=request.host,
                port=request.port,
                protocol=request.protocol,
                source=request.source,
                destination=request.destination,
                direction=request.direction,
            ).to_expression()

        output = Path(request.output).expanduser()
        session = CaptureSession(
            request.interface,
            output,
            filter_expression=expression or None,
            snaplen=request.snaplen,
            timeout=context.timeout,
        )

        started = time.perf_counter()
        try:
            await session.start()
        except (OSError, FileNotFoundError) as exc:
            return CaptureResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                output=str(output),
                interface=request.interface,
                expression=expression,
                warnings=[f"the capture could not be started: {exc}"],
            )

        await asyncio.sleep(request.duration)
        return_code = await session.stop()
        elapsed = time.perf_counter() - started

        size = output.stat().st_size if output.exists() else 0
        warnings: list[str] = []
        if return_code not in (0, 130, -signal.SIGINT):
            warnings.append(
                f"the capture tool exited with {return_code}: {'; '.join(session.stderr_lines[-3:])}"
            )

        return CaptureResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=elapsed * 1000.0,
            output=str(output),
            interface=request.interface,
            expression=expression,
            duration_seconds=elapsed,
            bytes_written=size,
            warnings=warnings,
        )
