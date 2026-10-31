"""The HTTP protocol.

The HTTP *protocol* client is the same engine as the HTTP *connectivity*
client, exposed here under the protocol taxonomy because it speaks a
specific protocol rather than reaching a host.  The two share the
implementation deliberately: there is one HTTP client in NetForge, not two.
"""

from __future__ import annotations

import time

from pydantic import Field

from netforge.connectivity.http import HttpConnection
from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel
from netforge.protocols.base import ProtocolAdapter, ProtocolResponse

__all__ = ["HttpProtocol", "HttpProtocolOperation"]

_logger = get_logger("protocols.http")


class HttpProtocol(ProtocolAdapter):
    """An HTTP client expressed as a protocol adapter."""

    protocol = "http"
    default_port = 80

    def __init__(
        self,
        host: str,
        port: int | None = None,
        *,
        timeout: float | None = 30.0,
        scheme: str = "http",
        path: str = "/",
        verify_tls: bool = True,
        user_agent: str = "netforge/0.1.0",
    ) -> None:
        super().__init__(host, port, timeout=timeout)
        self.scheme = scheme
        self.path = path
        self.verify_tls = verify_tls
        self.user_agent = user_agent
        self._client = HttpConnection(
            timeout=timeout, verify_tls=verify_tls, user_agent=user_agent
        )

    @property
    def url(self) -> str:
        """Return the base URL of the protocol endpoint."""
        default_port = 443 if self.scheme == "https" else 80
        netloc = self.host if self.port == default_port else f"{self.host}:{self.port}"
        return f"{self.scheme}://{netloc}{self.path}"

    async def connect(self) -> None:
        """HTTP has no session; the endpoint is reachable by construction."""
        self.connected = True

    async def close(self) -> None:
        """HTTP has no session to close."""
        self.connected = False

    async def exchange(self, payload: bytes) -> ProtocolResponse:
        """Send the payload as a POST body and return the response."""
        response = await self._client.request(self.url, method="POST", data=payload)
        return ProtocolResponse(
            payload=response.body,
            metadata={
                "status": response.status,
                "reason": response.reason,
                "headers": response.headers,
                "elapsed_ms": response.elapsed_ms,
            },
        )


class HttpProtocolRequest(RequestModel):
    """Request of :class:`HttpProtocolOperation`."""

    url: str = Field(description="The absolute URL to request.")
    method: str = Field(default="GET", description="The HTTP method.")
    headers: dict[str, str] = Field(default_factory=dict, description="Extra request headers.")
    body: str | None = Field(default=None, description="The request body.")
    timeout: float | None = Field(default=None, gt=0.0, description="Timeout in seconds.")


class HttpProtocolResponse(ResponseModel):
    """Response of :class:`HttpProtocolOperation`."""

    url: str = Field(description="The URL that was requested.")
    method: str = Field(description="The HTTP method that was used.")
    status: int = Field(description="The status code of the response.")
    headers: dict[str, str] = Field(default_factory=dict, description="The headers of the response.")
    body: str = Field(default="", description="The body of the response.")
    elapsed_ms: float = Field(default=0.0, description="How long the request took, in milliseconds.")


class HttpProtocolOperation(Operation[HttpProtocolRequest, HttpProtocolResponse]):
    """Speak HTTP against an endpoint and report the reply."""

    name = "protocols.http.request"
    category = CapabilityCategory.PROTOCOLS
    risk_level = RiskLevel.SAFE
    summary = "Speak the HTTP protocol against an endpoint and report the reply."
    description = (
        "Performs an HTTP request and returns the status, the headers and the body. "
        "This is the protocol-level view of the HTTP capability; the connectivity "
        "operation offers the same thing with a different taxonomy."
    )
    tags = frozenset({"http", "protocol", "request"})

    request_model = HttpProtocolRequest
    response_model = HttpProtocolResponse

    async def execute(
        self, request: HttpProtocolRequest, context: ExecutionContext
    ) -> HttpProtocolResponse:
        """Perform the request."""
        client = HttpConnection(
            timeout=request.timeout if request.timeout is not None else context.timeout,
            verify_tls=context.config.verify_tls,
            user_agent=context.config.user_agent,
        )
        payload = request.body.encode("utf-8") if request.body is not None else None
        started = time.perf_counter()
        response = await client.request(
            request.url, method=request.method, data=payload, headers=request.headers
        )
        return HttpProtocolResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            url=request.url,
            method=request.method.upper(),
            status=response.status,
            headers=response.headers,
            body=response.text,
            elapsed_ms=response.elapsed_ms,
        )
