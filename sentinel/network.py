"""The network operations: watching the traffic, and reading it back.

Two operations, one engine:

``sentinel.network.analyse``
    reads a capture file and reports what is in it.  It needs nothing
    but the file, so it runs anywhere, it needs no privilege, and it
    gives the same answer every time.

``sentinel.network.monitor``
    watches an interface while it runs.  It needs the privilege to open
    a raw socket, and it writes the capture it made -- so that the
    offline analyser can be run over it afterwards, and so that nothing
    is lost when the monitor is stopped.

The monitor is a convenience; the analyser is the truth.  A capture is a
record, and a record can be read again.
"""

from __future__ import annotations

import asyncio
import signal
import time
from pathlib import Path

from pydantic import Field

from netforge.analysis import PcapDecoder, read_pcap
from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.core.runner import which
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel
from netforge.sentinel.alerts import Alert, write_alerts
from netforge.sentinel.engine import Sentinel, Thresholds
from netforge.sentinel.rules import the_default_rules

__all__ = [
    "NetworkAnalysisRequest",
    "NetworkAnalysisResponse",
    "NetworkAnalysisOperation",
    "NetworkMonitorRequest",
    "NetworkMonitorResponse",
    "NetworkMonitorOperation",
]

_logger = get_logger("sentinel.network")

#: The tool that writes a capture to its standard output.
CAPTURE_TOOL = "tcpdump"


class NetworkAnalysisRequest(RequestModel):
    """Request of :class:`NetworkAnalysisOperation`."""

    path: str = Field(description="The capture file to read.")
    window_seconds: float = Field(
        default=60.0, gt=0.0, description="The window the rules look at."
    )
    distinct_ports: int = Field(
        default=10, ge=1, description="How many different ports make a sweep."
    )
    half_open: int = Field(
        default=5, ge=1, description="How many closed ports make a half-open scan."
    )
    silent_handshakes: int = Field(
        default=10, ge=1, description="How many empty connections make a scan."
    )
    service_probes: int = Field(
        default=3, ge=1, description="How many probed ports make a service probe."
    )


class NetworkAnalysisResponse(ResponseModel):
    """Response of :class:`NetworkAnalysisOperation`."""

    path: str = Field(description="The capture file that was read.")
    alerts: list[Alert] = Field(default_factory=list, description="What was found.")
    packets: int = Field(default=0, description="How many packets were read.")
    attempts: int = Field(default=0, description="How many connection attempts were seen.")
    sources: int = Field(default=0, description="How many addresses took part.")
    duration_ms: float = Field(default=0.0, description="How long the analysis took.")


class NetworkMonitorRequest(RequestModel):
    """Request of :class:`NetworkMonitorOperation`."""

    interface: str = Field(default="any", description="The interface to watch.")
    duration: float = Field(
        default=60.0, gt=0.0, le=86400.0, description="How long to watch for."
    )
    expression: str | None = Field(
        default=None, description="A BPF filter to narrow what is watched."
    )
    output: str | None = Field(
        default=None, description="The capture file to write, so that it can be read again."
    )
    sink: str | None = Field(
        default=None, description="The file the alerts are appended to, as JSON Lines."
    )
    snaplen: int = Field(default=65535, ge=64, le=262144, description="How many bytes of each packet to keep.")
    window_seconds: float = Field(
        default=60.0, gt=0.0, description="The window the rules look at."
    )
    distinct_ports: int = Field(
        default=10, ge=1, description="How many different ports make a sweep."
    )
    half_open: int = Field(
        default=5, ge=1, description="How many closed ports make a half-open scan."
    )
    silent_handshakes: int = Field(
        default=10, ge=1, description="How many empty connections make a scan."
    )
    service_probes: int = Field(
        default=3, ge=1, description="How many probed ports make a service probe."
    )


class NetworkMonitorResponse(ResponseModel):
    """Response of :class:`NetworkMonitorOperation`."""

    interface: str = Field(description="The interface that was watched.")
    alerts: list[Alert] = Field(default_factory=list, description="What was found.")
    packets: int = Field(default=0, description="How many packets were seen.")
    attempts: int = Field(default=0, description="How many connection attempts were seen.")
    output: str | None = Field(default=None, description="The capture file that was written.")
    sink: str | None = Field(default=None, description="The file the alerts were written to.")
    duration_seconds: float = Field(default=0.0, description="How long the monitor ran.")
    warnings: list[str] = Field(default_factory=list, description="What went wrong, if anything.")


def the_thresholds(request: NetworkAnalysisRequest | NetworkMonitorRequest) -> Thresholds:
    """The thresholds a request asks for."""
    return Thresholds(
        distinct_ports=request.distinct_ports,
        half_open=request.half_open,
        silent_handshakes=request.silent_handshakes,
        service_probes=request.service_probes,
    )


class NetworkAnalysisOperation(Operation[NetworkAnalysisRequest, NetworkAnalysisResponse]):
    """Read a capture and report the scans in it."""

    name = "sentinel.network.analyse"
    category = CapabilityCategory.SECURITY
    risk_level = RiskLevel.SAFE
    summary = "Read a capture file and report the scans that are in it."
    description = (
        "Reads a libpcap file, rebuilds the connection attempts it holds and reports "
        "the scans among them: a sweep over many ports, a half-open scan, a burst of "
        "empty connections, and a service probe. The file is only read, so the "
        "operation is declared at the safe level."
    )
    tags = frozenset({"detection", "scan", "pcap", "forensics"})

    request_model = NetworkAnalysisRequest
    response_model = NetworkAnalysisResponse

    async def execute(
        self, request: NetworkAnalysisRequest, context: ExecutionContext
    ) -> NetworkAnalysisResponse:
        """Read the capture and report what is in it."""
        started = time.perf_counter()
        path = Path(request.path)
        if not path.exists():
            return NetworkAnalysisResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                path=request.path,
                warnings=[f"{path} does not exist"],
            )

        try:
            packets = read_pcap(path)
        except (OSError, ValueError) as exc:
            return NetworkAnalysisResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                path=request.path,
                warnings=[f"the capture could not be read: {exc}"],
            )

        sentinel = Sentinel(
            window_seconds=request.window_seconds,
            rules=the_default_rules(the_thresholds(request)),
        )
        for packet in packets:
            sentinel.feed(packet)

        alerts = sentinel.evaluate()
        sources = {attempt.source for attempt in sentinel.the_attempts}
        return NetworkAnalysisResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            path=request.path,
            alerts=alerts,
            packets=len(packets),
            attempts=sentinel.attempts_seen,
            sources=len(sources),
        )


class NetworkMonitorOperation(Operation[NetworkMonitorRequest, NetworkMonitorResponse]):
    """Watch an interface and report the scans that go past."""

    name = "sentinel.network.monitor"
    category = CapabilityCategory.SECURITY
    risk_level = RiskLevel.OBSERVABILITY
    summary = "Watch an interface and report the scans that go past."
    description = (
        "Watches an interface with tcpdump and reports the scans it sees while it "
        "runs. The capture it made is written to a file, so that the same traffic can "
        "be read again with sentinel.network.analyse. Opening a raw socket needs a "
        "privilege, so the operation is declared at the observability level."
    )
    tags = frozenset({"detection", "scan", "live", "monitor", "ids"})
    requires_privilege = True

    request_model = NetworkMonitorRequest
    response_model = NetworkMonitorResponse

    async def execute(
        self, request: NetworkMonitorRequest, context: ExecutionContext
    ) -> NetworkMonitorResponse:
        """Watch the interface."""
        started = time.perf_counter()
        warnings: list[str] = []

        if which(CAPTURE_TOOL) is None:
            return NetworkMonitorResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                interface=request.interface,
                warnings=[f"{CAPTURE_TOOL} is not installed"],
            )

        sentinel = Sentinel(
            window_seconds=request.window_seconds,
            rules=the_default_rules(the_thresholds(request)),
        )

        argv = [
            CAPTURE_TOOL,
            "-i",
            request.interface,
            "-w",
            "-",
            "-s",
            str(request.snaplen),
        ]
        if request.expression:
            argv.append(request.expression)

        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        capture: Path | None = None
        handle = None
        if request.output:
            capture = Path(request.output)
            capture.parent.mkdir(parents=True, exist_ok=True)
            handle = capture.open("wb")

        decoder = PcapDecoder("the capture")
        packets = 0
        alerts: list[Alert] = []

        async def read_the_stream() -> None:
            nonlocal packets
            assert process.stdout is not None
            while True:
                chunk = await process.stdout.read(65536)
                if not chunk:
                    break
                if handle is not None:
                    handle.write(chunk)
                try:
                    decoded = decoder.feed(chunk)
                except ValueError as exc:
                    warnings.append(str(exc))
                    break
                for packet in decoded:
                    sentinel.feed(packet)
                    packets += 1

        async def drain_the_errors() -> None:
            assert process.stderr is not None
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    _logger.debug("the capture said: %s", text)

        async def watch() -> None:
            while True:
                await asyncio.sleep(1.0)
                for alert in sentinel.evaluate():
                    alerts.append(alert)
                    if request.sink:
                        write_alerts(request.sink, [alert])

        reader = asyncio.create_task(read_the_stream())
        errors = asyncio.create_task(drain_the_errors())
        watcher = asyncio.create_task(watch())

        try:
            await asyncio.sleep(request.duration)
        finally:
            watcher.cancel()
            reader.cancel()
            # tcpdump flushes its buffer and closes the stream when it is
            # interrupted; killing it would cut the capture short.
            try:
                process.send_signal(signal.SIGINT)
            except ProcessLookupError:
                # The tool had already finished on its own.
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=10.0)
            except TimeoutError:  # pragma: no cover - the tool ignored the signal
                process.kill()
                await process.wait()
            for task in (errors,):
                task.cancel()
            if handle is not None:
                handle.close()

        # Whatever was found in the last moments of the session, and
        # which the watcher did not yet see.
        remaining = sentinel.evaluate()
        if remaining:
            alerts.extend(remaining)
            if request.sink:
                write_alerts(request.sink, remaining)

        elapsed = time.perf_counter() - started
        return NetworkMonitorResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=elapsed * 1000.0,
            duration_seconds=elapsed,
            interface=request.interface,
            alerts=alerts,
            packets=packets,
            attempts=sentinel.attempts_seen,
            output=str(capture) if capture else None,
            sink=request.sink,
            warnings=warnings,
        )
