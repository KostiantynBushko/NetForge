"""Banner grabbing.

A banner is the string a service sends before it is asked anything: the
SSH version, the SMTP greeting, the HTTP response line.  It identifies the
software and often its version, which is exactly what an assessment needs.

Some services send their banner unprompted and some wait to be spoken to.
The grabber knows both: it reads first, and if nothing arrives it sends the
protocol's usual probe -- ``\\r\\n`` for FTP, ``HEAD / HTTP/1.0\\r\\n\\r\\n``
for HTTP -- and reads again.
"""

from __future__ import annotations

import asyncio
import time

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["BannerGrabOperation", "grab_banner", "PROBES"]

_logger = get_logger("security.banner")

#: The probe that is sent when a service does not speak first.
PROBES: dict[str, bytes] = {
    "ftp": b"\r\n",
    "smtp": b"EHLO netforge\r\n",
    "pop3": b"\r\n",
    "imap": b"a001 CAPABILITY\r\n",
    "http": b"HEAD / HTTP/1.0\r\n\r\n",
    "https": b"HEAD / HTTP/1.0\r\n\r\n",
}


async def grab_banner(
    host: str,
    port: int,
    *,
    probe: bytes | None = None,
    timeout: float = 3.0,
    read_size: int = 1024,
) -> tuple[str | None, bytes | None]:
    """Grab the banner of a service.

    Returns ``(banner, raw_bytes)``; the banner is the decoded text.
    """
    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        try:
            data = await asyncio.wait_for(reader.read(read_size), timeout=timeout)
        except asyncio.TimeoutError:
            data = b""
            if probe:
                writer.write(probe)
                await writer.drain()
                try:
                    data = await asyncio.wait_for(reader.read(read_size), timeout=timeout)
                except asyncio.TimeoutError:
                    data = b""
    except (OSError, asyncio.TimeoutError):
        return None, None
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, asyncio.TimeoutError):  # pragma: no cover - best effort
                pass

    if not data:
        return None, None
    return data.decode("utf-8", errors="replace").strip(), data


class BannerGrabRequest(RequestModel):
    """Request of :class:`BannerGrabOperation`."""

    host: str = Field(min_length=1, description="The host to talk to.")
    port: int = Field(ge=1, le=65535, description="The port to talk to.")
    protocol: str | None = Field(
        default=None,
        description="The protocol name, used to pick the probe: http, ftp, smtp, ...",
    )
    timeout: float | None = Field(default=3.0, gt=0.0, description="Read timeout in seconds.")


class BannerGrabResponse(ResponseModel):
    """Response of :class:`BannerGrabOperation`."""

    host: str = Field(description="The host the banner came from.")
    port: int = Field(description="The port the banner came from.")
    banner: str | None = Field(default=None, description="The banner, as text.")
    raw: str | None = Field(default=None, description="The banner, as it was received.")
    bytes: int = Field(default=0, description="How many bytes the banner holds.")


class BannerGrabOperation(Operation[BannerGrabRequest, BannerGrabResponse]):
    """Read the banner of a service."""

    name = "security.banner"
    category = CapabilityCategory.SECURITY
    risk_level = RiskLevel.OBSERVABILITY
    summary = "Read the banner a service sends when a client connects."
    description = (
        "Connects to a service and reads the banner it sends, optionally sending the "
        "protocol's usual probe first. The connection is visible to the service, which "
        "is why the operation is declared at the observability level."
    )
    tags = frozenset({"banner", "grab", "fingerprint", "service"})

    request_model = BannerGrabRequest
    response_model = BannerGrabResponse

    async def execute(
        self, request: BannerGrabRequest, context: ExecutionContext
    ) -> BannerGrabResponse:
        """Grab the banner."""
        probe = PROBES.get((request.protocol or "").lower())
        started = time.perf_counter()
        banner, raw = await grab_banner(
            request.host,
            request.port,
            probe=probe,
            timeout=request.timeout or 3.0,
        )
        return BannerGrabResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            host=request.host,
            port=request.port,
            banner=banner,
            raw=raw.decode("utf-8", errors="replace") if raw else None,
            bytes=len(raw) if raw else 0,
        )
