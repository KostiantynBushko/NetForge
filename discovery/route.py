"""The routing table.

``/proc/net/route`` holds the IPv4 routing table and ``/proc/net/ipv6_route``
the IPv6 one.  Both are text, both are readable without privilege, and
both are parsed here by pure functions.

The hexadecimal encoding in ``/proc/net/route`` is worth stating plainly:
the destination and the gateway are 32-bit values in *host* byte order,
printed as eight hexadecimal digits.  ``0102A8C0`` is ``192.168.2.1``.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["RouteEntry", "RouteTableOperation", "parse_route_table", "ROUTE_TABLE_PATH"]

#: Where Linux keeps the IPv4 routing table.
ROUTE_TABLE_PATH = Path("/proc/net/route")

#: Where Linux keeps the IPv6 routing table.
IPV6_ROUTE_TABLE_PATH = Path("/proc/net/ipv6_route")

# The flags column of /proc/net/route.
_RT_UP = 0x0001
_RT_GATEWAY = 0x0002


@dataclass(frozen=True)
class RouteEntry:
    """One row of the routing table."""

    destination: str
    gateway: str
    netmask: str
    device: str
    metric: int = 0
    flags: int = 0
    protocol: str = ""

    @property
    def is_up(self) -> bool:
        """Return ``True`` when the route is administratively up."""
        return bool(self.flags & _RT_UP)

    @property
    def is_gateway(self) -> bool:
        """Return ``True`` when the route is via a gateway."""
        return bool(self.flags & _RT_GATEWAY)

    def to_dict(self) -> dict[str, object]:
        """Return the entry as a plain dictionary."""
        return {
            "destination": self.destination,
            "gateway": self.gateway,
            "netmask": self.netmask,
            "device": self.device,
            "metric": self.metric,
            "flags": self.flags,
            "protocol": self.protocol,
            "is_up": self.is_up,
        }


def _hex_to_address(value: str) -> str:
    """Convert eight hexadecimal digits in host byte order to a dotted address."""
    try:
        raw = struct.pack("<I", int(value, 16))
    except ValueError:
        return value
    return socket.inet_ntoa(raw)


def parse_route_table(text: str) -> list[RouteEntry]:
    """Parse the contents of ``/proc/net/route``.

    Rows that do not have the expected eight fields are skipped rather than
    raising, so a kernel that changes the format degrades the capability
    instead of breaking it.
    """
    entries: list[RouteEntry] = []
    for index, line in enumerate((text or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        if index == 0 and line.lower().startswith("iface"):
            continue
        fields = line.split()
        if len(fields) < 8:
            continue
        try:
            flags = int(fields[3], 16)
            metric = int(fields[6], 16)
        except ValueError:
            continue
        # The columns of /proc/net/route are:
        #   Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT
        entries.append(
            RouteEntry(
                destination=_hex_to_address(fields[1]),
                gateway=_hex_to_address(fields[2]),
                netmask=_hex_to_address(fields[7]),
                device=fields[0],
                metric=metric,
                flags=flags,
                protocol=fields[4],
            )
        )
    return entries


class RouteTableRequest(RequestModel):
    """Request of :class:`RouteTableOperation`."""

    path: str = Field(
        default=str(ROUTE_TABLE_PATH),
        description="The file to read. Defaults to the kernel's IPv4 routing table.",
    )


class RouteTableResponse(ResponseModel):
    """Response of :class:`RouteTableOperation`."""

    entries: list[dict[str, object]] = Field(default_factory=list, description="The routes of the table.")
    source: str = Field(default="", description="Where the table was read from.")
    total: int = Field(default=0, description="How many routes there are.")


class RouteTableOperation(Operation[RouteTableRequest, RouteTableResponse]):
    """Read the local routing table."""

    name = "discovery.route.table"
    category = CapabilityCategory.DISCOVERY
    risk_level = RiskLevel.SAFE
    summary = "Read the local routing table."
    description = (
        "Reads the kernel's routing table and returns the destination, the gateway, the "
        "netmask, the interface and the metric of every route."
    )
    tags = frozenset({"route", "routing", "local", "gateway"})

    request_model = RouteTableRequest
    response_model = RouteTableResponse

    async def execute(
        self, request: RouteTableRequest, context: ExecutionContext
    ) -> RouteTableResponse:
        """Read and parse the table."""
        path = Path(request.path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return RouteTableResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                entries=[],
                source=str(path),
                total=0,
                warnings=[f"the routing table could not be read: {exc}"],
            )

        entries = parse_route_table(text)
        return RouteTableResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            entries=[entry.to_dict() for entry in entries],
            source=str(path),
            total=len(entries),
        )
