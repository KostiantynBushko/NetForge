"""The discovery capability: the parsers are pure, so they are tested offline."""

from __future__ import annotations

import pytest

from netforge.core.context import ExecutionContext
from netforge.discovery.arp import parse_arp_table
from netforge.discovery.ping import parse_ping_output
from netforge.discovery.route import parse_route_table
from netforge.discovery.service import lookup_service_name
from netforge.discovery.sweep import expand_network
from netforge.discovery.traceroute import parse_traceroute_output

LINUX_PING = """
PING 10.0.0.1 (10.0.0.1) 56(84) bytes of data.
64 bytes from 10.0.0.1: icmp_seq=1 ttl=64 time=0.045 ms
64 bytes from 10.0.0.1: icmp_seq=2 ttl=64 time=0.062 ms

--- 10.0.0.1 ping statistics ---
2 packets transmitted, 2 received, 0% packet loss, time 1002ms
rtt min/avg/max/mdev = 0.045/0.053/0.062/0.008 ms
"""

BSD_PING = """
PING 10.0.0.1 (10.0.0.1): 56 data bytes
64 bytes from 10.0.0.1: icmp_seq=0 ttl=64 time=0.052 ms
64 bytes from 10.0.0.1: icmp_seq=1 ttl=64 time=0.084 ms

--- 10.0.0.1 ping statistics ---
2 packets transmitted, 2 packets received, 0.0% packet loss
round-trip min/avg/max/stddev = 0.052/0.068/0.084/0.016 ms
"""

ARP_TABLE = """IP address       HW type     Flags       HW address            Mask     Device
192.168.1.1     0x1         0x2         aa:bb:cc:dd:ee:ff     *        eth0
192.168.1.55    0x1         0x0         00:00:00:00:00:00     *        eth0
"""

# The columns of /proc/net/route, in the order the kernel writes them:
#   Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT
ROUTE_TABLE = (
    "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n"
    "eth0\t00000000\t0102A8C0\t0003\t0\t0\t0\t00000000\t0\t0\t0\n"
    "eth0\t0002A8C0\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0\n"
)


class TestPingParsing:
    def test_the_linux_shape_is_understood(self):
        result = parse_ping_output(LINUX_PING)
        assert result.reachable is True
        assert result.loss_percent == 0.0
        assert result.avg_ms == 0.053
        assert result.min_ms == 0.045
        assert result.max_ms == 0.062

    def test_the_bsd_shape_is_understood(self):
        result = parse_ping_output(BSD_PING)
        assert result.reachable is True
        assert result.loss_percent == 0.0
        assert result.avg_ms == 0.068

    def test_a_total_loss_is_reported_as_unreachable(self):
        result = parse_ping_output("2 packets transmitted, 0 received, 100% packet loss")
        assert result.reachable is False
        assert result.loss_percent == 100.0

    def test_an_empty_output_is_not_a_crash(self):
        result = parse_ping_output("")
        assert result.reachable is False


class TestArpParsing:
    def test_the_table_is_parsed(self):
        entries = parse_arp_table(ARP_TABLE)
        assert len(entries) == 2
        assert entries[0].ip_address == "192.168.1.1"
        assert entries[0].mac_address == "aa:bb:cc:dd:ee:ff"
        assert entries[0].device == "eth0"

    def test_an_unresolved_entry_is_not_complete(self):
        entries = parse_arp_table(ARP_TABLE)
        assert entries[0].is_complete is True
        assert entries[1].is_complete is False

    def test_a_truncated_row_is_skipped(self):
        entries = parse_arp_table("IP address HW type\n192.168.1.1 0x1\n")
        assert entries == []


class TestRouteParsing:
    def test_the_routes_are_parsed(self):
        entries = parse_route_table(ROUTE_TABLE)
        assert len(entries) == 2
        assert entries[0].destination == "0.0.0.0"
        assert entries[0].gateway == "192.168.2.1"
        assert entries[0].device == "eth0"
        assert entries[0].is_up is True
        assert entries[0].is_gateway is True

    def test_the_netmask_is_converted_from_hexadecimal(self):
        entries = parse_route_table(ROUTE_TABLE)
        assert entries[1].netmask == "255.255.255.0"

    def test_a_truncated_row_is_skipped(self):
        assert parse_route_table("Iface Destination\neth0 0000\n") == []


class TestNetworkExpansion:
    def test_a_cidr_expands_to_its_hosts(self):
        hosts = expand_network("192.168.1.0/29")
        assert hosts == [
            "192.168.1.1",
            "192.168.1.2",
            "192.168.1.3",
            "192.168.1.4",
            "192.168.1.5",
            "192.168.1.6",
        ]

    def test_a_range_expands(self):
        assert expand_network("10.0.0.1-10.0.0.3") == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

    def test_a_single_address_expands(self):
        assert expand_network("10.0.0.1") == ["10.0.0.1"]

    def test_a_too_large_network_is_refused(self):
        with pytest.raises(ValueError, match="more than the limit"):
            expand_network("10.0.0.0/8")

    def test_a_backwards_range_is_refused(self):
        with pytest.raises(ValueError, match="ends before it starts"):
            expand_network("10.0.0.9-10.0.0.1")


class TestTracerouteParsing:
    def test_the_hops_are_parsed(self):
        hops = parse_traceroute_output(
            " 1  10.0.0.1  0.452 ms  0.398 ms\n"
            " 2  * * *\n"
            " 3  93.184.216.34  12.104 ms  11.987 ms\n"
        )
        assert len(hops) == 3
        assert hops[0]["address"] == "10.0.0.1"
        assert hops[0]["rtts_ms"] == [0.452, 0.398]
        assert hops[1]["timeout"] is True
        assert hops[2]["address"] == "93.184.216.34"


class TestServiceNames:
    def test_a_known_port_is_named(self):
        assert lookup_service_name(22) in {"ssh", None}

    def test_an_unknown_port_has_no_name(self):
        assert lookup_service_name(65533) is None


class TestDiscoveryOperations:
    async def test_the_ping_operation_uses_the_runner(self, registry, fake_runner):
        from tests.conftest import result

        fake_runner.responses["ping"] = result(LINUX_PING)
        operation = registry.create("discovery.ping")
        context = ExecutionContext(command_runner=fake_runner)

        response = await operation.run_request({"host": "10.0.0.1"}, context)
        assert response.reachable is True
        assert response.avg_ms == 0.053
        assert fake_runner.calls[0][0] == "ping"

    async def test_the_ping_operation_reports_a_missing_tool(self, registry, fake_runner):
        operation = registry.create("discovery.ping")
        context = ExecutionContext(command_runner=fake_runner)

        response = await operation.run_request({"host": "10.0.0.1"}, context)
        assert response.reachable is False
        assert response.warnings

    async def test_the_arp_operation_reads_the_file(self, registry, tmp_path):
        path = tmp_path / "arp"
        path.write_text(ARP_TABLE, encoding="utf-8")
        operation = registry.create("discovery.arp.table")

        response = await operation.run_request({"path": str(path)})
        assert response.total == 2
        assert response.entries[0]["ip_address"] == "192.168.1.1"

    async def test_the_arp_operation_reports_a_missing_file(self, registry, tmp_path):
        operation = registry.create("discovery.arp.table")
        response = await operation.run_request({"path": str(tmp_path / "absent")})
        assert response.total == 0
        assert response.warnings

    async def test_the_route_operation_reads_the_file(self, registry, tmp_path):
        path = tmp_path / "route"
        path.write_text(ROUTE_TABLE, encoding="utf-8")
        operation = registry.create("discovery.route.table")

        response = await operation.run_request({"path": str(path)})
        assert response.total == 2
        assert response.entries[0]["destination"] == "0.0.0.0"

    async def test_the_sweep_refuses_a_network_that_is_too_large(self, registry):
        operation = registry.create("discovery.ping.sweep")
        response = await operation.run_request({"network": "10.0.0.0/8", "max_hosts": 16})
        assert response.scanned == 0
