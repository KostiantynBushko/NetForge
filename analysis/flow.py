"""Flow analysis of capture files.

This module implements a libpcap reader and a flow aggregator on the
standard library alone.  That is a deliberate choice: the analysis of a
capture file is one of the things NetForge is *for*, and making it depend
on a packet library would put a third-party requirement in the middle of
the framework's core value.

The reader understands the two link types that matter in practice:

* ``LINKTYPE_ETHERNET`` (1) -- Ethernet II frames;
* ``LINKTYPE_RAW`` (101) -- bare IP packets;
* ``LINKTYPE_LINUX_SLL`` (113) -- the "cooked" capture Linux produces.

and the IPv4/IPv6, TCP/UDP/ICMP headers on top of them.
"""

from __future__ import annotations

import struct
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = [
    "Flow",
    "FlowAnalyzer",
    "FlowAnalysisOperation",
    "Packet",
    "read_pcap",
]

_logger = get_logger("analysis.flow")

LINKTYPE_ETHERNET = 1
LINKTYPE_RAW = 101
LINKTYPE_LINUX_SLL = 113

IPPROTO_TCP = 6
IPPROTO_UDP = 17
IPPROTO_ICMP = 1


@dataclass(slots=True)
class Packet:
    """One decoded packet."""

    timestamp: float
    length: int
    protocol: str = ""
    source: str = ""
    destination: str = ""
    source_port: int | None = None
    destination_port: int | None = None
    info: str = ""


@dataclass(slots=True)
class Flow:
    """An aggregated conversation between two endpoints."""

    source: str
    destination: str
    source_port: int | None
    destination_port: int | None
    protocol: str
    packets: int = 0
    bytes: int = 0
    first_seen: float = 0.0
    last_seen: float = 0.0
    flags: set[str] = field(default_factory=set)

    @property
    def key(self) -> tuple[str, int | None, str, int | None, str]:
        """Return the 5-tuple that identifies the flow."""
        return (self.source, self.source_port, self.destination, self.destination_port, self.protocol)

    @property
    def duration_seconds(self) -> float:
        """Return how long the flow lasted."""
        return max(0.0, self.last_seen - self.first_seen)

    @property
    def bytes_per_second(self) -> float:
        """Return the average throughput of the flow."""
        duration = self.duration_seconds
        if duration <= 0:
            return float(self.bytes)
        return self.bytes / duration

    def to_dict(self) -> dict[str, object]:
        """Return the flow as a plain dictionary."""
        return {
            "source": self.source,
            "source_port": self.source_port,
            "destination": self.destination,
            "destination_port": self.destination_port,
            "protocol": self.protocol,
            "packets": self.packets,
            "bytes": self.bytes,
            "duration_seconds": round(self.duration_seconds, 6),
            "bytes_per_second": round(self.bytes_per_second, 3),
            "flags": sorted(self.flags),
        }


def _ip_to_str(raw: bytes) -> str:
    return ".".join(str(byte) for byte in raw)


def _ipv6_to_str(raw: bytes) -> str:
    groups = [raw[index : index + 2].hex() for index in range(0, 16, 2)]
    return ":".join(groups)


def _parse_pcap_file(path: Path) -> tuple[int, list[Packet]]:
    """Read a libpcap file and return its link type and its packets."""
    data = path.read_bytes()
    if len(data) < 24:
        raise ValueError(f"{path} is too short to be a capture file")

    magic = data[:4]
    if magic == b"\xd4\xc3\xb2\xa1":
        endian, nanoseconds = "<", True
    elif magic == b"\xa1\xb2\xc3\xd4":
        endian, nanoseconds = ">", True
    elif magic == b"\x4d\x3c\xb2\xa1":
        endian, nanoseconds = "<", False
    elif magic == b"\xa1\xb2\x3c\x4d":
        endian, nanoseconds = ">", False
    else:
        raise ValueError(f"{path} is not a libpcap file (the magic is {magic.hex()})")

    link_type = struct.unpack_from(f"{endian}I", data, 20)[0]
    offset = 24
    packets: list[Packet] = []

    header = struct.Struct(f"{endian}IIII")
    while offset + 16 <= len(data):
        seconds, fraction, captured_len, original_len = header.unpack_from(data, offset)
        offset += 16
        payload = data[offset : offset + captured_len]
        offset += captured_len
        if len(payload) < captured_len:
            break

        timestamp = seconds + (fraction / 1_000_000_000.0 if nanoseconds else fraction / 1_000_000.0)
        packets.append(_decode_packet(payload, timestamp, original_len, link_type))

    return link_type, packets


def _decode_packet(payload: bytes, timestamp: float, original_len: int, link_type: int) -> Packet:
    """Decode one captured frame."""
    packet = Packet(timestamp=timestamp, length=original_len)

    offset = 0
    ethertype: int | None = None

    if link_type == LINKTYPE_ETHERNET:
        if len(payload) < 14:
            return packet
        ethertype = struct.unpack_from("!H", payload, 12)[0]
        offset = 14
        while ethertype in (0x8100, 0x88A8) and len(payload) >= offset + 4:
            ethertype = struct.unpack_from("!H", payload, offset + 2)[0]
            offset += 4
    elif link_type == LINKTYPE_LINUX_SLL:
        if len(payload) < 16:
            return packet
        ethertype = struct.unpack_from("!H", payload, 14)[0]
        offset = 16
    elif link_type == LINKTYPE_RAW:
        ethertype = 0x0800 if payload and payload[0] >> 4 == 4 else 0x86DD
    else:
        return packet

    if ethertype == 0x0800:
        return _decode_ipv4(payload, offset, packet)
    if ethertype == 0x86DD:
        return _decode_ipv6(payload, offset, packet)
    packet.protocol = f"ethertype:{ethertype:#06x}"
    return packet


def _decode_ipv4(payload: bytes, offset: int, packet: Packet) -> Packet:
    if len(payload) < offset + 20:
        return packet
    header_length = (payload[offset] & 0x0F) * 4
    protocol = payload[offset + 9]
    packet.source = _ip_to_str(payload[offset + 12 : offset + 16])
    packet.destination = _ip_to_str(payload[offset + 16 : offset + 20])
    packet.protocol = {IPPROTO_TCP: "tcp", IPPROTO_UDP: "udp", IPPROTO_ICMP: "icmp"}.get(protocol, f"ip:{protocol}")

    transport = offset + header_length
    if protocol == IPPROTO_TCP and len(payload) >= transport + 4:
        packet.source_port = struct.unpack_from("!H", payload, transport)[0]
        packet.destination_port = struct.unpack_from("!H", payload, transport + 2)[0]
        if len(payload) >= transport + 14:
            flags = payload[transport + 13]
            packet.info = _tcp_flags(flags)
    elif protocol == IPPROTO_UDP and len(payload) >= transport + 4:
        packet.source_port = struct.unpack_from("!H", payload, transport)[0]
        packet.destination_port = struct.unpack_from("!H", payload, transport + 2)[0]
        packet.info = f"len={struct.unpack_from('!H', payload, transport + 4)[0]}" if len(payload) >= transport + 6 else ""
    elif protocol == IPPROTO_ICMP:
        if len(payload) >= transport + 1:
            packet.info = f"type={payload[transport]}"
    return packet


def _decode_ipv6(payload: bytes, offset: int, packet: Packet) -> Packet:
    if len(payload) < offset + 40:
        return packet
    next_header = payload[offset + 6]
    packet.source = _ipv6_to_str(payload[offset + 8 : offset + 24])
    packet.destination = _ipv6_to_str(payload[offset + 24 : offset + 40])
    packet.protocol = {IPPROTO_TCP: "tcp", IPPROTO_UDP: "udp", IPPROTO_ICMP: "icmp"}.get(
        next_header, f"ipv6:{next_header}"
    )

    transport = offset + 40
    if next_header == IPPROTO_TCP and len(payload) >= transport + 4:
        packet.source_port = struct.unpack_from("!H", payload, transport)[0]
        packet.destination_port = struct.unpack_from("!H", payload, transport + 2)[0]
    elif next_header == IPPROTO_UDP and len(payload) >= transport + 4:
        packet.source_port = struct.unpack_from("!H", payload, transport)[0]
        packet.destination_port = struct.unpack_from("!H", payload, transport + 2)[0]
    return packet


def _tcp_flags(flags: int) -> str:
    names = []
    for bit, name in ((0x02, "SYN"), (0x10, "ACK"), (0x08, "PSH"), (0x01, "FIN"), (0x04, "RST")):
        if flags & bit:
            names.append(name)
    return ",".join(names)


def read_pcap(path: str | Path) -> list[Packet]:
    """Read a libpcap file and return its packets."""
    _link_type, packets = _parse_pcap_file(Path(path))
    return packets


class FlowAnalyzer:
    """Aggregates the packets of a capture file into flows."""

    def __init__(self, *, top: int = 50) -> None:
        self.top = top

    def analyze_packets(self, packets: list[Packet]) -> list[Flow]:
        """Aggregate ``packets`` into flows."""
        flows: dict[tuple[str, int | None, str, int | None, str], Flow] = {}
        for packet in packets:
            if not packet.source or not packet.destination:
                continue
            key = (packet.source, packet.source_port, packet.destination, packet.destination_port, packet.protocol)
            flow = flows.get(key)
            if flow is None:
                flow = Flow(
                    source=packet.source,
                    source_port=packet.source_port,
                    destination=packet.destination,
                    destination_port=packet.destination_port,
                    protocol=packet.protocol,
                    first_seen=packet.timestamp,
                    last_seen=packet.timestamp,
                )
                flows[key] = flow
            flow.packets += 1
            flow.bytes += packet.length
            flow.first_seen = min(flow.first_seen, packet.timestamp)
            flow.last_seen = max(flow.last_seen, packet.timestamp)
            if packet.info:
                flow.flags.update(part for part in packet.info.split(",") if part)
        return sorted(flows.values(), key=lambda flow: flow.bytes, reverse=True)

    def analyze(self, path: str | Path) -> list[Flow]:
        """Read a capture file and return its flows, largest first."""
        packets = read_pcap(path)
        flows = self.analyze_packets(packets)
        return flows[: self.top] if self.top else flows

    def statistics(self, flows: list[Flow]) -> dict[str, object]:
        """Return the aggregate statistics of ``flows``."""
        total_bytes = sum(flow.bytes for flow in flows)
        total_packets = sum(flow.packets for flow in flows)
        protocols: dict[str, int] = defaultdict(int)
        for flow in flows:
            protocols[flow.protocol] += flow.bytes
        return {
            "flows": len(flows),
            "packets": total_packets,
            "bytes": total_bytes,
            "protocols": dict(sorted(protocols.items(), key=lambda item: item[1], reverse=True)),
        }


class FlowAnalysisRequest(RequestModel):
    """Request of :class:`FlowAnalysisOperation`."""

    path: str = Field(description="The path of the capture file to analyse.")
    top: int = Field(default=50, ge=1, le=10000, description="How many flows to report.")


class FlowAnalysisResponse(ResponseModel):
    """Response of :class:`FlowAnalysisOperation`."""

    path: str = Field(description="The path of the capture file that was read.")
    flows: list[dict[str, object]] = Field(default_factory=list, description="The conversations of the capture, as a list of dictionaries.")
    statistics: dict[str, object] = Field(default_factory=dict, description="The statistics of the capture: the totals and the sizes.")


class FlowAnalysisOperation(Operation[FlowAnalysisRequest, FlowAnalysisResponse]):
    """Analyse a capture file and report its flows."""

    name = "analysis.flow"
    category = CapabilityCategory.ANALYSIS
    risk_level = RiskLevel.SAFE
    summary = "Analyse a capture file and report the conversations it contains."
    description = (
        "Reads a libpcap capture file, aggregates its packets into flows and reports the "
        "largest conversations with their sizes, their durations and the TCP flags they "
        "carried. The file is only read, so the operation is declared at the safe level."
    )
    tags = frozenset({"pcap", "flow", "analysis", "traffic"})

    request_model = FlowAnalysisRequest
    response_model = FlowAnalysisResponse

    async def execute(
        self, request: FlowAnalysisRequest, context: ExecutionContext
    ) -> FlowAnalysisResponse:
        """Analyse the capture."""
        started = time.perf_counter()
        path = Path(request.path).expanduser()
        analyzer = FlowAnalyzer(top=request.top)
        try:
            flows = analyzer.analyze(path)
        except (OSError, ValueError) as exc:
            return FlowAnalysisResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                path=str(path),
                flows=[],
                statistics={},
                warnings=[f"the capture could not be analysed: {exc}"],
            )

        return FlowAnalysisResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            path=str(path),
            flows=[flow.to_dict() for flow in flows],
            statistics=analyzer.statistics(flows),
        )
