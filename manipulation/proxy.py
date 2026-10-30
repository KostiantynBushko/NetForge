"""Traffic manipulation.

The proxies here are *controlled* manipulation: they forward traffic
faithfully, and the control is in what the operator configures -- the
listen address, the upstream address, whether the connection is allowed.

A plain TCP proxy is transparent to the protocol it carries.  An HTTP
proxy understands the request line and the ``CONNECT`` method, so it can
carry HTTPS through the tunnel without reading it.

Both are declared at the **manipulation** level: they are in the path of
the traffic, and the traffic they carry can be observed and changed.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.exceptions import OperationExecutionError
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["ProxyOperation", "ProxyRequest", "ProxyResponse", "TcpProxy", "run_tcp_proxy"]

_logger = get_logger("manipulation.proxy")


@dataclass(slots=True)
class ProxyStats:
    """What a proxy has done so far."""

    connections: int = 0
    bytes_client_to_upstream: int = 0
    bytes_upstream_to_client: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Return the statistics as a plain dictionary."""
        return {
            "connections": self.connections,
            "bytes_client_to_upstream": self.bytes_client_to_upstream,
            "bytes_upstream_to_client": self.bytes_upstream_to_client,
            "total_bytes": self.bytes_client_to_upstream + self.bytes_upstream_to_client,
            "errors": list(self.errors),
        }


class TcpProxy:
    """A transparent TCP proxy."""

    def __init__(
        self,
        listen_host: str,
        listen_port: int,
        upstream_host: str,
        upstream_port: int,
        *,
        timeout: float | None = 30.0,
    ) -> None:
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.timeout = timeout
        self.stats = ProxyStats()
        self._server: asyncio.AbstractServer | None = None

    async def _pump(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str) -> None:
        try:
            while True:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                if direction == "upstream":
                    self.stats.bytes_client_to_upstream += len(chunk)
                else:
                    self.stats.bytes_upstream_to_client += len(chunk)
                writer.write(chunk)
                await writer.drain()
        except (OSError, asyncio.CancelledError):
            pass
        finally:
            try:
                writer.close()
            except OSError:  # pragma: no cover - best effort
                pass

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.stats.connections += 1
        try:
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection(self.upstream_host, self.upstream_port),
                timeout=self.timeout,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            self.stats.errors.append(f"the upstream could not be reached: {exc}")
            writer.close()
            return

        await asyncio.gather(
            self._pump(reader, upstream_writer, "upstream"),
            self._pump(upstream_reader, writer, "client"),
        )

    async def start(self) -> None:
        """Start listening."""
        self._server = await asyncio.start_server(self._handle, self.listen_host, self.listen_port)

    async def stop(self) -> None:
        """Stop listening."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @property
    def port(self) -> int:
        """Return the port the proxy is listening on."""
        if self._server is not None and self._server.sockets:
            return int(self._server.sockets[0].getsockname()[1])
        return self.listen_port


async def run_tcp_proxy(
    listen_host: str,
    listen_port: int,
    upstream_host: str,
    upstream_port: int,
    *,
    duration: float | None = None,
    timeout: float | None = 30.0,
) -> ProxyStats:
    """Run a TCP proxy for ``duration`` seconds and return its statistics."""
    proxy = TcpProxy(
        listen_host, listen_port, upstream_host, upstream_port, timeout=timeout
    )
    await proxy.start()
    try:
        if duration:
            await asyncio.sleep(duration)
        else:
            await asyncio.Event().wait()
    finally:
        await proxy.stop()
    return proxy.stats


class ProxyRequest(RequestModel):
    """Request of :class:`ProxyOperation`."""

    listen_host: str = Field(default="127.0.0.1", description="The address to listen on.")
    listen_port: int = Field(default=0, ge=0, le=65535, description="The port to listen on. 0 for any.")
    upstream_host: str = Field(min_length=1, description="The host to forward to.")
    upstream_port: int = Field(ge=1, le=65535, description="The port to forward to.")
    duration: float | None = Field(default=10.0, gt=0.0, description="How long to run the proxy.")


class ProxyResponse(ResponseModel):
    """Response of :class:`ProxyOperation`."""

    listen_host: str = Field(description="The address the proxy listens on.")
    listen_port: int = Field(description="The port the proxy listens on.")
    upstream: str = Field(description="The host and port the traffic is forwarded to.")
    statistics: dict[str, object] = Field(default_factory=dict, description="What the proxy has forwarded so far.")


class ProxyOperation(Operation[ProxyRequest, ProxyResponse]):
    """Run a TCP proxy that forwards to an upstream host."""

    name = "manipulation.tcp.proxy"
    category = CapabilityCategory.MANIPULATION
    risk_level = RiskLevel.MANIPULATION
    summary = "Run a TCP proxy that forwards traffic to an upstream host and port."
    description = (
        "Runs a TCP proxy that accepts connections on one address and forwards them to "
        "another. The proxy sits in the path of the traffic, so the operation is "
        "declared at the manipulation level."
    )
    tags = frozenset({"proxy", "tcp", "forward", "intercept"})

    request_model = ProxyRequest
    response_model = ProxyResponse

    async def execute(self, request: ProxyRequest, context: ExecutionContext) -> ProxyResponse:
        """Run the proxy."""
        started = time.perf_counter()
        try:
            stats = await run_tcp_proxy(
                request.listen_host,
                request.listen_port,
                request.upstream_host,
                request.upstream_port,
                duration=request.duration,
                timeout=context.timeout,
            )
        except OSError as exc:
            raise OperationExecutionError(f"the proxy could not be started: {exc}") from exc

        return ProxyResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            listen_host=request.listen_host,
            listen_port=request.listen_port,
            upstream=f"{request.upstream_host}:{request.upstream_port}",
            statistics=stats.to_dict(),
        )
