"""The analysis capability: a libpcap file is written, read and analysed."""

from __future__ import annotations

import struct

from netforge.analysis.flow import FlowAnalyzer, read_pcap


def _ipv4_checksum(header: bytes) -> int:
    total = 0
    for index in range(0, len(header), 2):
        total += (header[index] << 8) + header[index + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def _tcp_packet(
    source: str,
    destination: str,
    source_port: int,
    destination_port: int,
    *,
    payload: bytes = b"",
    flags: int = 0x18,
    timestamp: float = 1_700_000_000.0,
) -> bytes:
    """Build one Ethernet/IPv4/TCP frame."""
    import socket

    tcp = struct.pack(
        "!HHIIBBHHH",
        source_port,
        destination_port,
        1,
        1,
        5 << 4,
        flags,
        65535,
        0,
        0,
    ) + payload

    source_bytes = socket.inet_aton(source)
    destination_bytes = socket.inet_aton(destination)
    total_length = 20 + len(tcp)
    ip_header = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        total_length,
        0x1234,
        0,
        64,
        6,
        0,
        source_bytes,
        destination_bytes,
    )
    checksum = _ipv4_checksum(ip_header)
    ip_header = ip_header[:10] + struct.pack("!H", checksum) + ip_header[12:]

    ethernet = b"\xaa\xbb\xcc\xdd\xee\xff" + b"\x00\x11\x22\x33\x44\x55" + b"\x08\x00"
    return ethernet + ip_header + tcp


def _write_pcap(path, packets: list[tuple[float, bytes]]) -> None:
    """Write a libpcap file."""
    with open(path, "wb") as handle:
        handle.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
        for timestamp, payload in packets:
            seconds = int(timestamp)
            microseconds = int((timestamp - seconds) * 1_000_000)
            handle.write(struct.pack("<IIII", seconds, microseconds, len(payload), len(payload)))
            handle.write(payload)


class TestPcapReading:
    def test_the_packets_are_read(self, tmp_path):
        path = tmp_path / "capture.pcap"
        _write_pcap(
            path,
            [
                (1_700_000_000.0, _tcp_packet("10.0.0.1", "10.0.0.2", 1234, 80, payload=b"x" * 10)),
                (1_700_000_001.0, _tcp_packet("10.0.0.2", "10.0.0.1", 80, 1234, payload=b"y" * 100)),
            ],
        )

        packets = read_pcap(path)
        assert len(packets) == 2
        assert packets[0].source == "10.0.0.1"
        assert packets[0].destination == "10.0.0.2"
        assert packets[0].source_port == 1234
        assert packets[0].destination_port == 80
        assert packets[0].protocol == "tcp"
        assert packets[0].length == 64  # 14 Ethernet + 20 IP + 20 TCP + 10 payload
    def test_the_tcp_flags_are_decoded(self, tmp_path):
        path = tmp_path / "flags.pcap"
        _write_pcap(
            path,
            [(1_700_000_000.0, _tcp_packet("10.0.0.1", "10.0.0.2", 1, 2, flags=0x02))],
        )
        packets = read_pcap(path)
        assert "SYN" in packets[0].info

    def test_a_file_that_is_not_a_capture_is_refused(self, tmp_path):
        path = tmp_path / "not.pcap"
        path.write_bytes(b"this is not a capture file at all")
        try:
            read_pcap(path)
        except ValueError as exc:
            assert "libpcap" in str(exc)
        else:  # pragma: no cover - the read must fail
            raise AssertionError("a file that is not a capture was accepted")


class TestFlowAnalysis:
    def test_the_packets_are_aggregated_into_flows(self, tmp_path):
        path = tmp_path / "capture.pcap"
        _write_pcap(
            path,
            [
                (1_700_000_000.0, _tcp_packet("10.0.0.1", "10.0.0.2", 1234, 80, payload=b"x" * 10)),
                (1_700_000_001.0, _tcp_packet("10.0.0.1", "10.0.0.2", 1234, 80, payload=b"x" * 20)),
                (1_700_000_002.0, _tcp_packet("10.0.0.2", "10.0.0.1", 80, 1234, payload=b"y" * 100)),
            ],
        )

        analyzer = FlowAnalyzer()
        flows = analyzer.analyze(path)
        assert len(flows) == 2

        largest = flows[0]
        assert largest.source == "10.0.0.2"
        assert largest.destination == "10.0.0.1"
        assert largest.packets == 1
        assert largest.bytes == 154  # 14 + 20 + 20 + 100

        smaller = flows[1]
        assert smaller.packets == 2
        assert smaller.duration_seconds == 1.0

    def test_the_statistics_are_computed(self, tmp_path):
        path = tmp_path / "capture.pcap"
        _write_pcap(
            path,
            [
                (1_700_000_000.0, _tcp_packet("10.0.0.1", "10.0.0.2", 1234, 80, payload=b"x" * 10)),
                (1_700_000_001.0, _tcp_packet("10.0.0.2", "10.0.0.1", 80, 1234, payload=b"y" * 100)),
            ],
        )

        analyzer = FlowAnalyzer()
        flows = analyzer.analyze(path)
        statistics = analyzer.statistics(flows)
        assert statistics["flows"] == 2
        assert statistics["packets"] == 2
        assert statistics["bytes"] > 0
        assert statistics["protocols"]["tcp"] > 0


class TestAnalysisOperation:
    async def test_the_operation_reports_the_flows(self, registry, tmp_path):
        path = tmp_path / "capture.pcap"
        _write_pcap(
            path,
            [
                (1_700_000_000.0, _tcp_packet("10.0.0.1", "10.0.0.2", 1234, 80, payload=b"x" * 10)),
                (1_700_000_001.0, _tcp_packet("10.0.0.2", "10.0.0.1", 80, 1234, payload=b"y" * 100)),
            ],
        )

        operation = registry.create("analysis.flow")
        response = await operation.run_request({"path": str(path)})
        assert len(response.flows) == 2
        assert response.statistics["flows"] == 2

    async def test_a_missing_capture_is_reported(self, registry, tmp_path):
        operation = registry.create("analysis.flow")
        response = await operation.run_request({"path": str(tmp_path / "absent.pcap")})
        assert response.flows == []
        assert response.warnings
