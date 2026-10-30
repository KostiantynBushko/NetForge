"""OPC UA.

OPC UA is a large protocol -- binary encoding, sessions, subscriptions,
an address space -- and a full client needs one.  ``asyncua`` is the
optional extra that provides it, and it is imported lazily.

What is implemented *here* is the part that is worth having without the
client: the endpoint.  An OPC UA endpoint URL carries the security
configuration in itself -- the scheme names the transport and the security
policy, the port names the profile -- and an operator who is auditing a
device wants exactly that, whether or not a session can be established.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlparse

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.exceptions import DependencyMissingError
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["OpcUaEndpoint", "OpcUaOperation", "OPCUA_EXTRA", "parse_endpoint"]

_logger = get_logger("protocols.opcua")

OPCUA_EXTRA = "opcua"

#: The transport schemes of OPC UA and what they mean.
SECURITY_PROFILES: dict[str, str] = {
    "opc.tcp": "None (no encryption, no signing)",
    "opc.tcps": "Sign and Encrypt",
    "opc.wss": "Secure WebSocket transport",
    "https": "HTTPS",
    "http": "HTTP",
}


@dataclass(frozen=True, slots=True)
class OpcUaEndpoint:
    """A parsed OPC UA endpoint."""

    url: str
    scheme: str
    host: str
    port: int | None
    path: str
    security_profile: str

    def to_dict(self) -> dict[str, object]:
        """Return the endpoint as a plain dictionary."""
        return {
            "url": self.url,
            "scheme": self.scheme,
            "host": self.host,
            "port": self.port,
            "path": self.path,
            "security_profile": self.security_profile,
            "encrypted": self.security_profile != SECURITY_PROFILES["opc.tcp"],
        }


def parse_endpoint(url: str) -> OpcUaEndpoint:
    """Parse an OPC UA endpoint URL."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if not scheme:
        raise ValueError(f"{url!r} carries no scheme")
    security_profile = SECURITY_PROFILES.get(scheme, f"Unknown ({scheme})")
    return OpcUaEndpoint(
        url=url,
        scheme=scheme,
        host=parsed.hostname or "",
        port=parsed.port,
        path=parsed.path or "/",
        security_profile=security_profile,
    )


class OpcUaRequest(RequestModel):
    """Request of :class:`OpcUaOperation`."""

    url: str = Field(min_length=1, description="The OPC UA endpoint URL.")
    connect: bool = Field(default=False, description="Also try to open a session.")


class OpcUaResponse(ResponseModel):
    """Response of :class:`OpcUaOperation`."""

    url: str = Field(description="The endpoint that was described.")
    endpoint: dict[str, object] = Field(default_factory=dict, description="The endpoint as the server reported it.")
    connected: bool = Field(default=False, description="Whether a session was opened.")
    nodes: list[str] = Field(default_factory=list, description="The nodes of the endpoint.")


class OpcUaOperation(Operation[OpcUaRequest, OpcUaResponse]):
    """Describe an OPC UA endpoint and optionally connect to it."""

    name = "protocols.opcua.endpoint"
    category = CapabilityCategory.PROTOCOLS
    risk_level = RiskLevel.SAFE
    summary = "Describe an OPC UA endpoint and optionally open a session."
    description = (
        "Parses an OPC UA endpoint URL and reports the transport, the port and the "
        "security profile it implies. With connect set, a session is opened as well, "
        "which needs the optional asyncua extra."
    )
    tags = frozenset({"opcua", "industrial", "endpoint"})

    request_model = OpcUaRequest
    response_model = OpcUaResponse

    async def execute(self, request: OpcUaRequest, context: ExecutionContext) -> OpcUaResponse:
        """Describe the endpoint."""
        started = time.perf_counter()
        try:
            endpoint = parse_endpoint(request.url)
        except ValueError as exc:
            return OpcUaResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                url=request.url,
                endpoint={},
                warnings=[str(exc)],
            )

        connected = False
        nodes: list[str] = []
        warnings: list[str] = []

        if request.connect:
            try:
                asyncua = _load_asyncua()
            except DependencyMissingError as exc:
                warnings.append(str(exc))
            else:
                try:
                    async with asyncua.Client(url=request.url) as client:
                        nodes = [node.nodeid.to_string() for node in client.nodes.root.get_children()]
                    connected = True
                except Exception as exc:  # noqa: BLE001 - a session may fail in many ways
                    warnings.append(f"the session could not be opened: {exc}")

        return OpcUaResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            url=request.url,
            endpoint=endpoint.to_dict(),
            connected=connected,
            nodes=nodes,
            warnings=warnings,
        )


def _load_asyncua():
    try:
        import asyncua  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise DependencyMissingError(
            "asyncua",
            extra=OPCUA_EXTRA,
            feature="OPC UA sessions",
        ) from exc
    import asyncua

    return asyncua
