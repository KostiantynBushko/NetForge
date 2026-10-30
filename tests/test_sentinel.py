"""The sentinel: the engine, the rules, the parsers and the operations.

Everything here runs offline.  The capture is a file that the test
writes, the logs are lines the test writes, and the monitor is fed by a
script that pretends to be tcpdump.
"""

from __future__ import annotations

from netforge.analysis.flow import Packet
from netforge.core.context import ExecutionContext
from netforge.sentinel.alerts import (
    Alert,
    Severity,
    read_alerts,
    write_alerts,
)
from netforge.sentinel.engine import Sentinel, Thresholds
from netforge.sentinel.logs import (
    parse_access_log,
    parse_syslog,
    parse_ufw,
)
from netforge.sentinel.rules import the_default_rules
from tests.test_analysis import _tcp_packet, _write_pcap

SYN = 0x02
ACK = 0x10
PSH = 0x08
FIN = 0x01
RST = 0x04


def a_packet(
    source: str,
    destination: str,
    source_port: int,
    destination_port: int,
    *,
    flags: int = SYN,
    payload: bytes = b"",
    timestamp: float = 1_700_000_000.0,
) -> Packet:
    """Build one decoded packet."""
    from netforge.analysis.flow import decode_packet

    frame = _tcp_packet(
        source,
        destination,
        source_port,
        destination_port,
        payload=payload,
        flags=flags,
        timestamp=timestamp,
    )
    return decode_packet(frame, timestamp, len(frame), 1)


def a_scan(source: str, destination: str, ports: list[int], *, half_open: bool = False):
    """Build the packets of a scan, and the packets of a normal client."""
    packets = []
    base = 1_700_000_000.0
    for index, port in enumerate(ports):
        moment = base + index * 0.05
        source_port = 40000 + index
        packets.append(
            a_packet(source, destination, source_port, port, flags=SYN, timestamp=moment)
        )
        if half_open:
            packets.append(
                a_packet(
                    destination,
                    source,
                    port,
                    source_port,
                    flags=RST | ACK,
                    timestamp=moment + 0.001,
                )
            )
        else:
            packets.append(
                a_packet(
                    destination,
                    source,
                    port,
                    source_port,
                    flags=SYN | ACK,
                    timestamp=moment + 0.001,
                )
            )
            packets.append(
                a_packet(
                    source,
                    destination,
                    source_port,
                    port,
                    flags=ACK,
                    timestamp=moment + 0.002,
                )
            )
    return packets


class TestTheEngine:
    """What the engine makes of the packets it is fed."""

    def test_a_syn_starts_an_attempt(self):
        sentinel = Sentinel()
        sentinel.feed(a_packet("10.0.0.1", "10.0.0.2", 40000, 22, flags=SYN))
        assert sentinel.attempts_seen == 1

    def test_the_handshake_completes_the_attempt(self):
        sentinel = Sentinel()
        sentinel.feed(a_packet("10.0.0.1", "10.0.0.2", 40000, 22, flags=SYN))
        sentinel.feed(a_packet("10.0.0.2", "10.0.0.1", 22, 40000, flags=SYN | ACK))
        sentinel.feed(a_packet("10.0.0.1", "10.0.0.2", 40000, 22, flags=ACK))
        attempt = sentinel.the_attempts[0]
        assert attempt.completed is True
        assert attempt.state == "open"

    def test_a_reset_leaves_the_port_closed(self):
        sentinel = Sentinel()
        sentinel.feed(a_packet("10.0.0.1", "10.0.0.2", 40000, 22, flags=SYN))
        sentinel.feed(a_packet("10.0.0.2", "10.0.0.1", 22, 40000, flags=RST | ACK))
        attempt = sentinel.the_attempts[0]
        assert attempt.reset is True
        assert attempt.state == "reset"

    def test_the_payload_of_the_source_is_counted(self):
        sentinel = Sentinel()
        sentinel.feed(a_packet("10.0.0.1", "10.0.0.2", 40000, 22, flags=SYN))
        sentinel.feed(
            a_packet(
                "10.0.0.1",
                "10.0.0.2",
                40000,
                22,
                flags=PSH | ACK,
                payload=b"GET / HTTP/1.0\r\n",
            )
        )
        attempt = sentinel.the_attempts[0]
        assert attempt.payload_from_source > 0
        assert attempt.probed is True

    def test_the_banner_of_the_target_is_not_a_probe(self):
        sentinel = Sentinel()
        sentinel.feed(a_packet("10.0.0.1", "10.0.0.2", 40000, 22, flags=SYN))
        sentinel.feed(
            a_packet(
                "10.0.0.2",
                "10.0.0.1",
                22,
                40000,
                flags=PSH | ACK,
                payload=b"SSH-2.0-OpenSSH_10.2\r\n",
            )
        )
        attempt = sentinel.the_attempts[0]
        assert attempt.payload_from_target > 0
        assert attempt.probed is False

    def test_the_window_forgets_the_old_attempts(self):
        sentinel = Sentinel(window_seconds=10.0)
        sentinel.feed(a_packet("10.0.0.1", "10.0.0.2", 40000, 22, flags=SYN))
        assert sentinel.attempts_seen == 1
        sentinel.feed(
            a_packet(
                "10.0.0.1",
                "10.0.0.2",
                40001,
                23,
                flags=SYN,
                timestamp=1_700_000_100.0,
            )
        )
        assert sentinel.attempts_seen == 1

    def test_an_alert_is_reported_once(self):
        sentinel = Sentinel(rules=the_default_rules(Thresholds(distinct_ports=3)))
        for packet in a_scan("10.0.0.1", "10.0.0.2", [21, 22, 23]):
            sentinel.feed(packet)
        assert len(sentinel.evaluate()) == 1
        assert sentinel.evaluate() == []


class TestTheNetworkRules:
    """What the rules find."""

    def the_sentinel(self, **thresholds) -> Sentinel:
        limits = Thresholds(**thresholds)
        return Sentinel(rules=the_default_rules(limits))

    def test_a_sweep_is_found(self):
        sentinel = self.the_sentinel(distinct_ports=5)
        for packet in a_scan("10.0.0.1", "10.0.0.2", [21, 22, 23, 25, 53]):
            sentinel.feed(packet)
        alerts = sentinel.evaluate()
        assert any(alert.rule == "port-sweep" for alert in alerts)
        alert = next(alert for alert in alerts if alert.rule == "port-sweep")
        assert alert.source == "10.0.0.1"
        assert alert.destination == "10.0.0.2"
        assert alert.evidence["distinct_ports"] == 5

    def test_a_quiet_network_is_not_a_scan(self):
        sentinel = self.the_sentinel(distinct_ports=5)
        for packet in a_scan("10.0.0.1", "10.0.0.2", [80]):
            sentinel.feed(packet)
        assert sentinel.evaluate() == []

    def test_a_half_open_scan_is_found(self):
        sentinel = self.the_sentinel(half_open=3, distinct_ports=100)
        for packet in a_scan(
            "10.0.0.1", "10.0.0.2", [21, 22, 23], half_open=True
        ):
            sentinel.feed(packet)
        alerts = sentinel.evaluate()
        assert any(alert.rule == "half-open-scan" for alert in alerts)

    def test_silent_connections_are_found(self):
        sentinel = self.the_sentinel(silent_handshakes=3, distinct_ports=100)
        for packet in a_scan("10.0.0.1", "10.0.0.2", [21, 22, 23]):
            sentinel.feed(packet)
        alerts = sentinel.evaluate()
        assert any(alert.rule == "silent-connections" for alert in alerts)

    def test_a_service_probe_is_found(self):
        sentinel = self.the_sentinel(service_probes=2, distinct_ports=100)
        for index, port in enumerate([22, 80]):
            moment = 1_700_000_000.0 + index * 0.05
            sentinel.feed(a_packet("10.0.0.1", "10.0.0.2", 40000 + index, port, flags=SYN))
            sentinel.feed(
                a_packet(
                    "10.0.0.1",
                    "10.0.0.2",
                    40000 + index,
                    port,
                    flags=PSH | ACK,
                    payload=b"probe\r\n",
                    timestamp=moment + 0.01,
                )
            )
        alerts = sentinel.evaluate()
        assert any(alert.rule == "service-probe" for alert in alerts)


class TestTheAlerts:
    """The alerts, and the file they are kept in."""

    def an_alert(self, **overrides) -> Alert:
        values = {
            "rule": "port-sweep",
            "severity": Severity.HIGH.value,
            "summary": "something happened",
            "source": "10.0.0.1",
            "destination": "10.0.0.2",
            "timestamp": 1_700_000_000.0,
            "evidence": {"distinct_ports": 12},
        }
        values.update(overrides)
        return Alert(**values)

    def test_the_alerts_are_written_and_read(self, tmp_path):
        path = tmp_path / "alerts.jsonl"
        assert write_alerts(path, [self.an_alert(), self.an_alert()]) == 2
        alerts = read_alerts(path)
        assert len(alerts) == 2
        assert alerts[0].rule == "port-sweep"

    def test_the_alerts_are_appended(self, tmp_path):
        path = tmp_path / "alerts.jsonl"
        write_alerts(path, [self.an_alert()])
        write_alerts(path, [self.an_alert()])
        assert len(read_alerts(path)) == 2

    def test_the_severity_can_be_filtered(self, tmp_path):
        path = tmp_path / "alerts.jsonl"
        write_alerts(
            path,
            [
                self.an_alert(),
                self.an_alert(rule="ssh-failure-burst", severity=Severity.LOW.value),
            ],
        )
        alerts = read_alerts(path, severity="low")
        assert len(alerts) == 1
        assert alerts[0].rule == "ssh-failure-burst"

    def test_the_rule_can_be_filtered(self, tmp_path):
        path = tmp_path / "alerts.jsonl"
        write_alerts(path, [self.an_alert(), self.an_alert(rule="web-scan")])
        assert len(read_alerts(path, rule="web-scan")) == 1

    def test_a_broken_line_is_skipped(self, tmp_path):
        path = tmp_path / "alerts.jsonl"
        write_alerts(path, [self.an_alert()])
        with path.open("a", encoding="utf-8") as handle:
            handle.write("{not json at all\n")
        assert len(read_alerts(path)) == 1

    def test_a_sink_that_does_not_exist_holds_nothing(self, tmp_path):
        assert read_alerts(tmp_path / "nothing.jsonl") == []


class TestTheLogParsers:
    """Reading the logs."""

    def test_the_failed_passwords_are_read(self):
        text = (
            "Jan 12 10:15:03 server sshd[1234]: Failed password for invalid user bob "
            "from 10.0.0.5 port 5678 ssh2\n"
        )
        events = parse_syslog(text)
        assert len(events) == 1
        assert events[0].action == "failed-password"
        assert events[0].source == "10.0.0.5"
        assert events[0].user == "bob"

    def test_the_accepted_logins_are_read(self):
        text = (
            "Jan 12 10:15:03 server sshd[1234]: Accepted publickey for bob from "
            "10.0.0.5 port 5678 ssh2\n"
        )
        events = parse_syslog(text)
        assert events[0].action == "accepted"

    def test_the_other_lines_are_left_alone(self):
        text = "Jan 12 10:15:03 server cron[999]: (root) CMD (/usr/bin/thing)\n"
        assert parse_syslog(text) == []

    def test_the_ufw_blocks_are_read(self):
        text = (
            "Jan 12 10:15:03 server kernel: [UFW BLOCK] IN=eth0 OUT= SRC=10.0.0.5 "
            "DST=10.0.0.2 PROTO=TCP SPT=1234 DPT=22\n"
        )
        events = parse_ufw(text)
        assert len(events) == 1
        assert events[0].action == "block"
        assert events[0].source == "10.0.0.5"
        assert events[0].port == 22

    def test_the_access_log_is_read(self):
        text = (
            '10.0.0.5 - - [12/Jan/2024:10:15:03 +0000] "GET /admin HTTP/1.1" 404 123 '
            '"-" "curl/8.0"\n'
        )
        events = parse_access_log(text)
        assert len(events) == 1
        assert events[0].source == "10.0.0.5"
        assert events[0].status == 404
        assert events[0].path == "/admin"


class TestTheOperations:
    """The operations themselves."""

    async def test_the_network_analysis_finds_the_scan(self, registry, tmp_path):
        path = tmp_path / "capture.pcap"
        frames = []
        base = 1_700_000_000.0
        for index, port in enumerate([21, 22, 23, 25, 53]):
            moment = base + index * 0.05
            frames.append(
                (
                    moment,
                    _tcp_packet("10.0.0.1", "10.0.0.2", 40000 + index, port, flags=SYN),
                )
            )
            frames.append(
                (
                    moment + 0.001,
                    _tcp_packet(
                        "10.0.0.2", "10.0.0.1", port, 40000 + index, flags=SYN | ACK
                    ),
                )
            )
            frames.append(
                (
                    moment + 0.002,
                    _tcp_packet("10.0.0.1", "10.0.0.2", 40000 + index, port, flags=ACK),
                )
            )
        _write_pcap(path, frames)

        operation = registry.create("sentinel.network.analyse")
        response = await operation.run_request(
            {"path": str(path), "distinct_ports": 5, "window_seconds": 300.0}
        )
        assert response.packets == 15
        assert response.attempts == 5
        assert any(alert.rule == "port-sweep" for alert in response.alerts)

    async def test_the_network_analysis_of_a_missing_file(self, registry, tmp_path):
        operation = registry.create("sentinel.network.analyse")
        response = await operation.run_request({"path": str(tmp_path / "nothing.pcap")})
        assert response.alerts == []
        assert response.warnings

    async def test_the_log_analysis_finds_the_burst(self, registry, tmp_path):
        path = tmp_path / "auth.log"
        lines = [
            f"Jan 12 10:15:{index:02d} server sshd[1234]: Failed password for invalid "
            f"user bob from 10.0.0.5 port 5678 ssh2"
            for index in range(12)
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        operation = registry.create("sentinel.log.analyse")
        response = await operation.run_request({"path": str(path), "failures": 10})
        assert response.events == 12
        assert any(alert.rule == "ssh-failure-burst" for alert in response.alerts)

    async def test_the_log_analysis_finds_the_refused_ports(self, registry, tmp_path):
        path = tmp_path / "ufw.log"
        lines = [
            f"Jan 12 10:15:{index:02d} server kernel: [UFW BLOCK] IN=eth0 OUT= "
            f"SRC=10.0.0.5 DST=10.0.0.2 PROTO=TCP SPT=1234 DPT={port}"
            for index, port in enumerate([21, 22, 23, 25, 53, 80, 110, 143, 443, 8080, 8443])
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        operation = registry.create("sentinel.log.analyse")
        response = await operation.run_request({"path": str(path), "blocked_ports": 10})
        assert any(alert.rule == "firewall-port-sweep" for alert in response.alerts)

    async def test_the_alerts_are_listed(self, registry, tmp_path):
        path = tmp_path / "alerts.jsonl"
        write_alerts(
            path,
            [
                Alert(
                    rule="port-sweep",
                    severity=Severity.HIGH.value,
                    summary="something happened",
                    source="10.0.0.1",
                )
            ],
        )
        operation = registry.create("sentinel.alert.list")
        response = await operation.run_request({"path": str(path)})
        assert response.total == 1
        assert response.by_rule == {"port-sweep": 1}
        assert response.by_severity == {"high": 1}

    async def test_the_monitor_reads_the_capture(self, registry, tmp_path, monkeypatch):
        capture = tmp_path / "capture.pcap"
        frames = [
            (
                1_700_000_000.0 + index * 0.05,
                _tcp_packet("10.0.0.1", "10.0.0.2", 40000 + index, port, flags=SYN),
            )
            for index, port in enumerate([21, 22, 23, 25, 53])
        ]
        _write_pcap(capture, frames)

        # A script that stands in for tcpdump: it writes the capture to
        # its standard output, which is what the real one does.
        tool = tmp_path / "fake-tcpdump"
        tool.write_text(f"#!/bin/sh\ncat {capture}\n", encoding="utf-8")
        tool.chmod(0o755)
        monkeypatch.setattr("netforge.sentinel.network.CAPTURE_TOOL", str(tool))

        operation = registry.create("sentinel.network.monitor")
        context = ExecutionContext()
        response = await operation.run_request(
            {
                "interface": "any",
                "duration": 1.0,
                "distinct_ports": 5,
                "output": str(tmp_path / "written.pcap"),
            },
            context,
        )
        assert response.packets == 5
        assert (tmp_path / "written.pcap").exists()
        assert any(alert.rule == "port-sweep" for alert in response.alerts)
