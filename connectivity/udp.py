"""UDP connectivity.

UDP has no session: there is no connect step that establishes state, only
a send that may or may not be answered.  The connection object here
therefore models the *endpoint* -- a local socket bound to a port, and the
remote address it talks to -- and the operation is the probe: send a
payload, wait for the answer, report what came back.

That distinction matters for the risk model: a UDP probe is read-only
observation, but it does send bytes to a third party, so it is declared at
level 2 (observability) rather than level 1.
"""

from __future__ import annotations

import asyncio
import time
from pydantic import Field

from netforge.connectivity.base import Connection, ConnectionState
from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["UdpConnection", "UdpProbeOperation"]

_logger = get_logger("connectivity.udp")


class _DatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, future: "asyncio.Future[bytes]") -> None:
        self._future = future

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if not self._future.done():
            self._future.set_result(data)

    def error_received(self, exc: Exception) -> None:  # pragma: no cover - network dependent
        if not self._future.done():
            self._future.set_exception(exc)


class UdpConnection(Connection):
    """A UDP endpoint bound to a local socket."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        local_host: str = "0.0.0.0",
        local_port: int = 0,
        timeout: float | None = 30.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.host = host
        self.port = port
        self.local_host = local_host
        self.local_port = local_port
        self._transport: asyncio.DatagramTransport | None = None

    async def connect(self) -> None:
        """Bind the local socket."""
        if self.is_connected:
            return
        self.state = ConnectionState.CONNECTING
        loop = asyncio.get_running_loop()
        try:
            transport, _protocol = await loop.create_datagram_endpoint(
                _DatagramProtocol,
                local_addr=(self.local_host, self.local_port),
            )
        except OSError as exc:
            self._mark_failed(exc)
            raise
        self._transport = transport
        self.state = ConnectionState.CONNECTED

    async def close(self) -> None:
        """Close the local socket."""
        transport, self._transport = self._transport, None
        if transport is not None:
            transport.close()
        self.state = ConnectionState.CLOSED

    async def send(self, payload: bytes) -> None:
        """Send ``payload`` to the remote endpoint."""
        if self._transport is None:
            raise ConnectionError("the connection is not open")
        self._transport.sendto(payload, (self.host, self.port))

    async def receive(self, *, timeout: float | None = None) -> bytes:
        """Wait for a datagram from the remote endpoint."""
        if self._transport is None:
            raise ConnectionError("the connection is not open")
        budget = self.timeout if timeout is None else timeout
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bytes] = loop.create_future()
        protocol = self._transport.get_protocol()
        assert isinstance(protocol, _DatagramProtocol)
        protocol._future = future
        try:
            if budget is None:
                return await future
            return await asyncio.wait_for(future, timeout=budget)
        finally:
            protocol._future = future  # keep the reference alive until the next call


class UdpProbeRequest(RequestModel):
    """Request of :class:`UdpProbeOperation`."""

    host: str = Field(description="The remote host.")
    port: int = Field(ge=1, le=65535, description="The remote UDP port.")
    payload: str = Field(default="netforge", description="The payload to send.")
    timeout: float | None = Field(default=5.0, gt=0.0, description="How long to wait for a reply.")
    local_port: int = Field(default=0, ge=0, le=65535, description="Local port to bind, 0 for any.")


class UdpProbeResponse(ResponseModel):
    """Response of :class:`UdpProbeOperation`."""

    host: str = Field(description="The host that was probed.")
    port: int = Field(description="The port that was probed.")
    replied: bool = Field(description="Whether the host answered.")
    latency_ms: float | None = Field(default=None, description="How long the answer took, in milliseconds.")
    reply: str | None = Field(default=None, description="The datagram that came back.")
    reply_bytes: int = Field(default=0, description="How many bytes the answer holds.")
    error: str | None = Field(default=None, description="Why the probe failed, when it did.")


class UdpProbeOperation(Operation[UdpProbeRequest, UdpProbeResponse]):
    """Send a UDP datagram and wait for the answer."""

    name = "connectivity.udp.probe"
    category = CapabilityCategory.CONNECTIVITY
    risk_level = RiskLevel.OBSERVABILITY
    summary = "Send a UDP datagram to a host and report whether it answered."
    description = (
        "Sends a datagram to the given UDP port and waits for a reply. The probe is "
        "read-only in intent -- nothing is changed on the remote host -- but it does "
        "put bytes on the wire, which is why it is declared at the observability level."
    )
    tags = frozenset({"udp", "probe", "reachability"})

    request_model = UdpProbeRequest
    response_model = UdpProbeResponse

    async def execute(
        self, request: UdpProbeRequest, context: ExecutionContext
    ) -> UdpProbeResponse:
        """Send the datagram and wait for the answer."""
        connection = UdpConnection(
            request.host,
            request.port,
            local_port=request.local_port,
            timeout=request.timeout,
        )
        started = time.perf_counter()
        try:
            await connection.connect()
            await connection.send(request.payload.encode("utf-8"))
            data = await connection.receive(timeout=request.timeout)
        except asyncio.TimeoutError:
            return UdpProbeResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                host=request.host,
                port=request.port,
                replied=False,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                error="no reply within the timeout",
            )
        except (OSError, ConnectionError) as exc:
            return UdpProbeResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                host=request.host,
                port=request.port,
                replied=False,
                error=str(exc) or type(exc).__name__,
            )
        finally:
            await connection.close()

        latency = (time.perf_counter() - started) * 1000.0
        return UdpProbeResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=latency,
            host=request.host,
            port=request.port,
            replied=True,
            latency_ms=latency,
            reply=data.decode("utf-8", errors="replace"),
            reply_bytes=len(data),
        )
