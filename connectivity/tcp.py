"""TCP connectivity.

A TCP connection is the simplest useful thing NetForge can do to a remote
host, and it is the substrate several other capabilities are built on: the
port scanner, the banner grabber, the proxy and the Modbus client all speak
TCP.

The ``TcpConnectOperation`` exposes the plain reachability check as an
operation, because "can I open a TCP session to this host and port" is a
question an operator and an agent both ask constantly.
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

__all__ = ["TcpConnectOperation", "TcpConnection"]

_logger = get_logger("connectivity.tcp")


class TcpConnection(Connection):
    """A TCP connection to a remote host and port."""

    def __init__(self, host: str, port: int, *, timeout: float | None = 30.0) -> None:
        super().__init__(timeout=timeout)
        self.host = host
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        """Open the TCP session."""
        if self.is_connected:
            return
        self.state = ConnectionState.CONNECTING
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
        except (TimeoutError, OSError) as exc:
            self._mark_failed(exc)
            raise
        self.state = ConnectionState.CONNECTED

    async def close(self) -> None:
        """Close the TCP session."""
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (TimeoutError, OSError):  # pragma: no cover - best effort
                pass
        self.state = ConnectionState.CLOSED

    async def write(self, data: bytes) -> None:
        """Send ``data`` over the connection."""
        if self._writer is None:
            raise ConnectionError("the connection is not open")
        self._writer.write(data)
        await self._writer.drain()

    async def read(self, size: int = 4096) -> bytes:
        """Read up to ``size`` bytes from the connection."""
        if self._reader is None:
            raise ConnectionError("the connection is not open")
        return await self._reader.read(size)

    async def exchange(self, data: bytes, *, read_size: int = 4096) -> bytes:
        """Send ``data`` and read the first chunk of the reply."""
        await self.write(data)
        return await self.read(read_size)


class TcpConnectRequest(RequestModel):
    """Request of :class:`TcpConnectOperation`."""

    host: str = Field(description="The host to connect to.")
    port: int = Field(ge=1, le=65535, description="The TCP port to connect to.")
    timeout: float | None = Field(default=None, gt=0.0, description="Connect timeout in seconds.")


class TcpConnectResponse(ResponseModel):
    """Response of :class:`TcpConnectOperation`."""

    host: str = Field(description="The host that was reached.")
    port: int = Field(description="The port that was reached.")
    reachable: bool = Field(description="Whether the connection succeeded.")
    latency_ms: float | None = Field(default=None, description="How long the connection took, in milliseconds.")
    local_address: str | None = Field(default=None, description="The address the connection was made from.")
    peer_address: str | None = Field(default=None, description="The address of the other end.")
    error: str | None = Field(default=None, description="Why the connection failed, when it did.")


class TcpConnectOperation(Operation[TcpConnectRequest, TcpConnectResponse]):
    """Check whether a TCP port accepts a connection."""

    name = "connectivity.tcp.connect"
    category = CapabilityCategory.CONNECTIVITY
    risk_level = RiskLevel.SAFE
    summary = "Open a TCP connection to a host and port and report whether it succeeded."
    description = (
        "Attempts a TCP connection to the given host and port and reports reachability, "
        "the time it took and the addresses involved. The connection is closed immediately "
        "afterwards; no data is sent."
    )
    tags = frozenset({"tcp", "reachability", "probe"})

    request_model = TcpConnectRequest
    response_model = TcpConnectResponse

    async def execute(
        self, request: TcpConnectRequest, context: ExecutionContext
    ) -> TcpConnectResponse:
        """Try to connect and report the outcome."""
        timeout = request.timeout if request.timeout is not None else context.timeout
        connection = TcpConnection(request.host, request.port, timeout=timeout)
        started = time.perf_counter()
        try:
            await connection.connect()
        except (TimeoutError, OSError, ConnectionError) as exc:
            latency = (time.perf_counter() - started) * 1000.0
            return TcpConnectResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=latency,
                host=request.host,
                port=request.port,
                reachable=False,
                latency_ms=latency,
                error=str(exc) or type(exc).__name__,
            )
        finally:
            await connection.close()

        latency = (time.perf_counter() - started) * 1000.0
        writer = connection._writer
        local = writer.get_extra_info("sockname") if writer is not None else None
        peer = writer.get_extra_info("peername") if writer is not None else None
        return TcpConnectResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=latency,
            host=request.host,
            port=request.port,
            reachable=True,
            latency_ms=latency,
            local_address=_format_address(local),
            peer_address=_format_address(peer),
        )


def _format_address(address: object) -> str | None:
    if address is None:
        return None
    if isinstance(address, tuple) and len(address) >= 2:
        return f"{address[0]}:{address[1]}"
    return str(address)
