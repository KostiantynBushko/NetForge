"""HTTP connectivity.

The HTTP client is built on :mod:`urllib.request` from the standard
library and run in a worker thread, so the framework keeps exactly one
hard dependency -- Pydantic -- and the HTTP capability works on a bare
Python installation.

That is a deliberate trade.  ``httpx`` or ``requests`` would be more
convenient, but they are third-party, and the specification's "Framework
First" principle says the networking logic must not drag an ecosystem along
with it.
"""

from __future__ import annotations

import asyncio
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["HttpConnection", "HttpRequestOperation", "HttpResponseData"]

_logger = get_logger("connectivity.http")

DEFAULT_USER_AGENT = "netforge/0.1.0"


@dataclass(slots=True)
class HttpResponseData:
    """The raw result of an HTTP exchange."""

    status: int
    reason: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    url: str = ""
    elapsed_ms: float = 0.0

    @property
    def text(self) -> str:
        """Return the body decoded as UTF-8, replacing undecodable bytes."""
        return self.body.decode("utf-8", errors="replace")


class HttpConnection:
    """A small HTTP client built on the standard library."""

    def __init__(
        self,
        *,
        timeout: float | None = 30.0,
        verify_tls: bool = True,
        user_agent: str = DEFAULT_USER_AGENT,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.timeout = timeout
        self.verify_tls = verify_tls
        self.user_agent = user_agent
        self.default_headers = dict(headers or {})

    def build_request(
        self,
        url: str,
        *,
        method: str = "GET",
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> urllib.request.Request:
        """Build the request object without sending it."""
        merged = {"User-Agent": self.user_agent, **self.default_headers, **(headers or {})}
        request = urllib.request.Request(url=url, data=data, method=method.upper())
        for key, value in merged.items():
            request.add_header(key, value)
        return request

    async def request(
        self,
        url: str,
        *,
        method: str = "GET",
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> HttpResponseData:
        """Perform an HTTP request and return the response.

        An HTTP error status is returned, not raised: a 404 is a perfectly
        good answer to a question, and the caller decides what it means.
        """
        budget = self.timeout if timeout is None else timeout
        request = self.build_request(url, method=method, data=data, headers=headers)
        started = time.perf_counter()

        def _do() -> tuple[int, str, dict[str, str], bytes]:
            context = None
            if not self.verify_tls:
                import ssl

                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            try:
                with urllib.request.urlopen(request, timeout=budget, context=context) as response:
                    body = response.read()
                    return (
                        int(response.status),
                        response.reason or "",
                        {k: v for k, v in response.headers.items()},
                        body,
                    )
            except urllib.error.HTTPError as exc:
                body = exc.read() if hasattr(exc, "read") else b""
                return int(exc.code), exc.reason or "", dict(exc.headers or {}), body

        try:
            status, reason, response_headers, body = await asyncio.to_thread(_do)
        except asyncio.TimeoutError:
            raise TimeoutError(f"the request to {url} timed out after {budget}s") from None
        except urllib.error.URLError as exc:
            raise ConnectionError(f"the request to {url} failed: {exc.reason}") from exc

        return HttpResponseData(
            status=status,
            reason=reason,
            headers=response_headers,
            body=body,
            url=url,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )


class HttpRequestRequest(RequestModel):
    """Request of :class:`HttpRequestOperation`."""

    url: str = Field(description="The absolute URL to request.")
    method: str = Field(default="GET", description="The HTTP method.")
    headers: dict[str, str] = Field(default_factory=dict, description="Extra request headers.")
    body: str | None = Field(default=None, description="Request body, sent as UTF-8.")
    timeout: float | None = Field(default=None, gt=0.0, description="Timeout in seconds.")
    max_body_bytes: int = Field(
        default=1_048_576,
        ge=0,
        description="How many bytes of the body to keep in the response.",
    )


class HttpRequestResponse(ResponseModel):
    """Response of :class:`HttpRequestOperation`."""

    url: str
    method: str
    status: int
    reason: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    body_bytes: int = 0
    truncated: bool = False
    elapsed_ms: float = 0.0


class HttpRequestOperation(Operation[HttpRequestRequest, HttpRequestResponse]):
    """Perform an HTTP request and report the response."""

    name = "connectivity.http.request"
    category = CapabilityCategory.CONNECTIVITY
    risk_level = RiskLevel.SAFE
    summary = "Perform an HTTP request and report the status, headers and body."
    description = (
        "Performs an HTTP request and returns the status code, the response headers and "
        "the body. The body is truncated to the requested size so that a large download "
        "cannot flood an agent's context."
    )
    tags = frozenset({"http", "https", "request"})

    request_model = HttpRequestRequest
    response_model = HttpRequestResponse

    async def execute(
        self, request: HttpRequestRequest, context: ExecutionContext
    ) -> HttpRequestResponse:
        """Perform the request."""
        client = HttpConnection(
            timeout=request.timeout if request.timeout is not None else context.timeout,
            verify_tls=context.config.verify_tls,
            user_agent=context.config.user_agent,
        )
        payload = request.body.encode("utf-8") if request.body is not None else None
        response = await client.request(
            request.url,
            method=request.method,
            data=payload,
            headers=request.headers,
        )

        total = len(response.body)
        keep = response.body[: request.max_body_bytes]
        return HttpRequestResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=response.elapsed_ms,
            url=request.url,
            method=request.method.upper(),
            status=response.status,
            reason=response.reason,
            headers=response.headers,
            body=keep.decode("utf-8", errors="replace"),
            body_bytes=total,
            truncated=total > len(keep),
            elapsed_ms=response.elapsed_ms,
        )
