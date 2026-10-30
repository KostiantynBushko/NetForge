"""The ARP table.

On Linux the neighbour table lives in ``/proc/net/arp``.  It is a small,
stable, comma-separated text format, and reading it needs no privilege at
all -- which makes it the cheapest useful piece of local network
information there is.

The parser is a pure function over text, so it can be checked against a
captured sample without a Linux kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["ArpEntry", "ArpTableOperation", "parse_arp_table", "ARP_TABLE_PATH"]

#: Where Linux keeps the neighbour table.
ARP_TABLE_PATH = Path("/proc/net/arp")


@dataclass(frozen=True)
class ArpEntry:
    """One row of the ARP table."""

    ip_address: str
    hw_type: str
    flags: str
    mac_address: str
    device: str

    @property
    def is_complete(self) -> bool:
        """Return ``True`` when the entry has a resolved hardware address."""
        return bool(self.mac_address) and self.mac_address != "00:00:00:00:00:00"

    def to_dict(self) -> dict[str, str]:
        """Return the entry as a plain dictionary."""
        return {
            "ip_address": self.ip_address,
            "hw_type": self.hw_type,
            "flags": self.flags,
            "mac_address": self.mac_address,
            "device": self.device,
        }


def parse_arp_table(text: str) -> list[ArpEntry]:
    """Parse the contents of ``/proc/net/arp``.

    The first line is a header and is skipped.  Rows that do not have the
    expected six fields are skipped as well rather than raising: a kernel
    that changes the format should degrade the capability, not break it.
    """
    entries: list[ArpEntry] = []
    for index, line in enumerate((text or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        if index == 0 and line.lower().startswith("ip address"):
            continue
        fields = [field.strip() for field in line.split()]
        if len(fields) < 6:
            continue
        entries.append(
            ArpEntry(
                ip_address=fields[0],
                hw_type=fields[1],
                flags=fields[2],
                mac_address=fields[3],
                # The mask sits between the hardware address and the device.
                device=fields[5] if len(fields) > 5 else fields[4],
            )
        )
    return entries


class ArpTableRequest(RequestModel):
    """Request of :class:`ArpTableOperation`."""

    path: str = Field(
        default=str(ARP_TABLE_PATH),
        description="The file to read. Defaults to the kernel's neighbour table.",
    )
    complete_only: bool = Field(default=False, description="Only return entries with a resolved MAC.")


class ArpTableResponse(ResponseModel):
    """Response of :class:`ArpTableOperation`."""

    entries: list[dict[str, str]] = Field(default_factory=list)
    source: str = ""
    total: int = 0


class ArpTableOperation(Operation[ArpTableRequest, ArpTableResponse]):
    """Read the local ARP / neighbour table."""

    name = "discovery.arp.table"
    category = CapabilityCategory.DISCOVERY
    risk_level = RiskLevel.SAFE
    summary = "Read the local ARP neighbour table."
    description = (
        "Reads the kernel's ARP neighbour table and returns the IP address, the hardware "
        "address, the flags and the interface of every entry. Reading the table changes "
        "nothing, so the operation is declared at the safe level."
    )
    tags = frozenset({"arp", "neighbour", "local", "mac"})

    request_model = ArpTableRequest
    response_model = ArpTableResponse

    async def execute(
        self, request: ArpTableRequest, context: ExecutionContext
    ) -> ArpTableResponse:
        """Read and parse the table."""
        path = Path(request.path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ArpTableResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                entries=[],
                source=str(path),
                total=0,
                warnings=[f"the table could not be read: {exc}"],
            )

        entries = parse_arp_table(text)
        if request.complete_only:
            entries = [entry for entry in entries if entry.is_complete]

        return ArpTableResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            entries=[entry.to_dict() for entry in entries],
            source=str(path),
            total=len(entries),
        )
