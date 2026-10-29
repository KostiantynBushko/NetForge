"""ICMP echo -- ping.

``ping`` is a system tool on every platform NetForge runs on, so the
capability shells out to it rather than opening a raw socket.  A raw
socket would need ``CAP_NET_RAW`` or root, and the capability would then
only work for the privileged: an unprivileged ping works for everybody.

The parsing is separate from the invocation, so the output of a captured
``ping`` run can be checked without running ``ping``.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["PingOperation", "PingResult", "parse_ping_output"]

_logger = get_logger("discovery.ping")

_LOSS_RE = re.compile(r"(?P<pct>\d+(?:\.\d+)?)%\s+packet loss", re.IGNORECASE)
_RTT_RE = re.compile(
    r"(?:rtt|round-trip)\s+min/avg/max(?:/(?:mdev|stddev))?\s*=\s*"
    r"(?P<min>[\d.]+)/(?P<avg>[\d.]+)/(?P<max>[\d.]+)",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"time[=<]\s*(?P<ms>[\d.]+)\s*ms", re.IGNORECASE)


@dataclass(slots=True)
class PingResult:
    """The parsed result of one ping."""

    reachable: bool
    loss_percent: float = 100.0
    min_ms: float | None = None
    avg_ms: float | None = None
    max_ms: float | None = None
    raw: str = ""

    @property
    def latency_ms(self) -> float | None:
        """Return the average round-trip time, when it was reported."""
        return self.avg_ms


def parse_ping_output(output: str) -> PingResult:
    """Parse the output of a ``ping`` run.

    Both the Linux (``ping`` from iputils) and the BSD/macOS shapes are
    understood, because their summary lines differ:

    * Linux  -- ``3 packets transmitted, 3 received, 0% packet loss``
    * BSD   -- ``3 packets transmitted, 3 packets received, 0.0% packet loss``

    and their round-trip lines differ too:

    * Linux  -- ``rtt min/avg/max/mdev = 0.045/0.062/0.086/0.018 ms``
    * BSD   -- ``round-trip min/avg/max/stddev = 0.052/0.068/0.084/0.016 ms``
    """
    text = output or ""
    result = PingResult(reachable=False, raw=text)

    loss = _LOSS_RE.search(text)
    if loss:
        result.loss_percent = float(loss.group("pct"))
        result.reachable = result.loss_percent < 100.0

    rtt = _RTT_RE.search(text)
    if rtt:
        result.min_ms = float(rtt.group("min"))
        result.avg_ms = float(rtt.group("avg"))
        result.max_ms = float(rtt.group("max"))
        result.reachable = True
    else:
        single = _TIME_RE.search(text)
        if single:
            value = float(single.group("ms"))
            result.min_ms = result.avg_ms = result.max_ms = value
            result.reachable = True

    return result


class PingRequest(RequestModel):
    """Request of :class:`PingOperation`."""

    host: str = Field(min_length=1, description="The host or address to ping.")
    count: int = Field(default=3, ge=1, le=100, description="How many echo requests to send.")
    timeout: float | None = Field(default=5.0, gt=0.0, description="Per-packet timeout in seconds.")


class PingResponse(ResponseModel):
    """Response of :class:`PingOperation`."""

    host: str
    reachable: bool
    loss_percent: float = 100.0
    min_ms: float | None = None
    avg_ms: float | None = None
    max_ms: float | None = None


class PingOperation(Operation[PingRequest, PingResponse]):
    """Ping a host and report whether it answers."""

    name = "discovery.ping"
    category = CapabilityCategory.DISCOVERY
    risk_level = RiskLevel.SAFE
    summary = "Send ICMP echo requests to a host and report the round-trip times."
    description = (
        "Pings a host with the system ping utility and reports whether it answered, the "
        "packet loss and the minimum, average and maximum round-trip times."
    )
    tags = frozenset({"icmp", "ping", "reachability"})

    request_model = PingRequest
    response_model = PingResponse

    async def execute(self, request: PingRequest, context: ExecutionContext) -> PingResponse:
        """Run the ping and parse its output."""
        runner = context.runner()
        argv = [
            "ping",
            "-c",
            str(request.count),
            "-W",
            str(max(1, int(request.timeout or 5))),
            request.host,
        ]
        started = time.perf_counter()
        try:
            result = await runner.run(argv, timeout=context.timeout)
        except Exception as exc:
            return PingResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                host=request.host,
                reachable=False,
                loss_percent=100.0,
                warnings=[f"ping could not be run: {exc}"],
            )

        parsed = parse_ping_output(f"{result.stdout}\n{result.stderr}")
        warnings: list[str] = []
        if not result.ok:
            detail = (result.stderr or result.stdout).strip()
            warnings.append(f"ping exited with the status {result.returncode}: {detail}")
        return PingResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            host=request.host,
            reachable=parsed.reachable,
            loss_percent=parsed.loss_percent,
            min_ms=parsed.min_ms,
            avg_ms=parsed.avg_ms,
            max_ms=parsed.max_ms,
            warnings=warnings,
        )
