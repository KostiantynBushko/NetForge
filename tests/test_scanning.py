"""The levels of a scan, and the nmap engine.

The levels are a table of numbers, and the engine is a command line and
a parser of XML.  Both are tested here without nmap and without a
network: the runner is faked, and the XML is a sample.
"""

from __future__ import annotations

import asyncio

import pytest

from netforge.core.context import ExecutionContext
from netforge.discovery import nmap
from netforge.models.scanning import (
    PROFILES,
    Aggressiveness,
    ScanEngine,
    ScanProfile,
    the_profile,
)

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<nmaprun scanner="nmap" args="nmap -sT -sV -Pn -n -T3 -oX - -- 10.0.0.1">
<host starttime="1700000000" endtime="1700000010"><status state="up" reason="user-set"/>
<address addr="10.0.0.1" addrtype="ipv4"/>
<ports>
<port protocol="tcp" portid="22"><state state="open" reason="syn-ack"/>
<service name="ssh" product="OpenSSH" version="10.2p1" method="probed" conf="10"/></port>
<port protocol="tcp" portid="80"><state state="open" reason="syn-ack"/>
<service name="http" product="Apache httpd" version="2.4.66" method="probed" conf="10"/></port>
<port protocol="tcp" portid="443"><state state="closed" reason="conn-refused"/>
<service name="https" method="table" conf="3"/></port>
<port protocol="tcp" portid="8080"><state state="filtered" reason="no-response"/>
<service name="http-alt" method="table" conf="3"/></port>
</ports>
</host>
<runstats><finished time="1700000010" elapsed="10.0"/></runstats>
</nmaprun>
"""


class TestTheLevels:
    """The levels, and the profiles behind them."""

    def test_there_are_five_levels(self):
        assert [level.value for level in Aggressiveness] == [
            "paranoid",
            "stealth",
            "polite",
            "normal",
            "aggressive",
        ]

    def test_a_level_is_parsed(self):
        assert Aggressiveness.parse("stealth") is Aggressiveness.STEALTH
        assert Aggressiveness.parse("POLITE") is Aggressiveness.POLITE
        assert Aggressiveness.parse("Aggressive") is Aggressiveness.AGGRESSIVE

    def test_an_unknown_level_is_refused(self):
        with pytest.raises(ValueError, match="unknown aggressiveness"):
            Aggressiveness.parse("reckless")

    def test_every_level_has_a_profile(self):
        assert set(PROFILES) == set(Aggressiveness)

    def test_the_normal_level_changes_nothing(self):
        profile = the_profile("normal")
        assert profile.concurrency is None
        assert profile.timeout is None
        assert profile.delay == 0.0

    def test_the_quiet_levels_are_slower(self):
        paranoid = the_profile("paranoid")
        stealth = the_profile("stealth")
        polite = the_profile("polite")
        normal = the_profile("normal")
        assert paranoid.delay > stealth.delay > polite.delay >= normal.delay

    def test_the_quiet_levels_probe_one_port_at_a_time(self):
        assert the_profile("paranoid").concurrency == 1
        assert the_profile("stealth").concurrency == 1

    def test_the_quiet_levels_are_more_patient(self):
        paranoid = the_profile("paranoid").the_timeout(2.0)
        stealth = the_profile("stealth").the_timeout(2.0)
        assert paranoid > stealth > 2.0

    def test_the_aggressive_level_is_the_other_way_round(self):
        aggressive = the_profile("aggressive")
        assert aggressive.concurrency > 32
        assert aggressive.delay == 0.0

    def test_a_profile_falls_back_to_the_default(self):
        profile = ScanProfile()
        assert profile.the_concurrency(64) == 64
        assert profile.the_timeout(2.0) == 2.0

    def test_a_profile_overrides_the_default(self):
        profile = ScanProfile(concurrency=1, timeout=9.0)
        assert profile.the_concurrency(64) == 1
        assert profile.the_timeout(2.0) == 9.0


class TestTheEngine:
    """The engine that runs the scan."""

    def test_there_are_two_engines(self):
        assert [engine.value for engine in ScanEngine] == ["native", "nmap"]

    def test_an_engine_is_parsed(self):
        assert ScanEngine.parse("nmap") is ScanEngine.NMAP
        assert ScanEngine.parse("NATIVE") is ScanEngine.NATIVE

    def test_an_unknown_engine_is_refused(self):
        with pytest.raises(ValueError, match="unknown scan engine"):
            ScanEngine.parse("masscan")


class TestTheNmapArguments:
    """The command line of nmap."""

    def the_arguments(self, **overrides):
        arguments = {
            "host": "10.0.0.1",
            "ports": "22,80",
            "level": Aggressiveness.NORMAL,
            "timeout": 2.0,
            "root": False,
        }
        arguments.update(overrides)
        return nmap.the_arguments(**arguments)

    def test_the_host_comes_last(self):
        arguments = self.the_arguments()
        assert arguments[0] == "nmap"
        assert arguments[-1] == "10.0.0.1"
        assert arguments[-2] == "--"

    def test_the_service_probes_are_asked_for(self):
        assert "-sV" in self.the_arguments()

    def test_the_host_is_not_pinged_first(self):
        assert "-Pn" in self.the_arguments()

    def test_the_ports_are_given(self):
        arguments = self.the_arguments(ports="22,80")
        assert arguments[arguments.index("-p") + 1] == "22,80"

    def test_the_result_is_xml_on_the_standard_output(self):
        arguments = self.the_arguments()
        assert arguments[arguments.index("-oX") + 1] == "-"

    def test_each_level_has_its_timing_template(self):
        for level, template in (
            (Aggressiveness.PARANOID, "-T0"),
            (Aggressiveness.STEALTH, "-T1"),
            (Aggressiveness.POLITE, "-T2"),
            (Aggressiveness.NORMAL, "-T3"),
            (Aggressiveness.AGGRESSIVE, "-T4"),
        ):
            arguments = self.the_arguments(level=level)
            assert template in arguments, level

    def test_a_connect_scan_is_used_without_root(self):
        assert "-sT" in self.the_arguments(root=False)

    def test_a_half_open_scan_is_used_with_root(self):
        arguments = self.the_arguments(level=Aggressiveness.STEALTH, root=True)
        assert "-sS" in arguments
        assert "-sT" not in arguments

    def test_the_other_levels_are_connect_scans_even_with_root(self):
        arguments = self.the_arguments(level=Aggressiveness.POLITE, root=True)
        assert "-sT" in arguments
        assert "-sS" not in arguments

    def test_the_warning_of_a_half_open_scan_without_root(self):
        warnings = nmap.the_warnings(Aggressiveness.STEALTH, root=False)
        assert warnings and "root" in warnings[0]

    def test_there_is_no_warning_when_the_scan_can_be_half_open(self):
        assert nmap.the_warnings(Aggressiveness.STEALTH, root=True) == []

    def test_the_other_levels_have_no_warning(self):
        assert nmap.the_warnings(Aggressiveness.NORMAL, root=False) == []


class TestTheNmapOutput:
    """The XML that nmap writes."""

    def test_the_open_ports_are_read(self):
        found = nmap.parse_nmap_xml(SAMPLE_XML)
        assert found.open_ports == [22, 80]

    def test_the_closed_ports_are_read(self):
        found = nmap.parse_nmap_xml(SAMPLE_XML)
        assert found.closed_ports == [443]

    def test_the_filtered_ports_are_read(self):
        found = nmap.parse_nmap_xml(SAMPLE_XML)
        assert found.filtered_ports == [8080]

    def test_the_service_is_read(self):
        found = nmap.parse_nmap_xml(SAMPLE_XML)
        open_ports = found.the_open()
        assert open_ports[0]["service"] == "ssh"

    def test_the_version_is_read(self):
        found = nmap.parse_nmap_xml(SAMPLE_XML)
        open_ports = found.the_open()
        assert open_ports[0]["version"] == "OpenSSH 10.2p1"

    def test_the_ports_are_counted(self):
        found = nmap.parse_nmap_xml(SAMPLE_XML)
        assert found.scanned == 4

    def test_a_host_that_is_down_is_a_warning(self):
        xml = '<nmaprun><host><status state="down"/></host></nmaprun>'
        found = nmap.parse_nmap_xml(xml)
        assert found.scanned == 0
        assert found.warnings

    def test_output_that_is_not_xml_is_refused(self):
        with pytest.raises(ValueError, match="not valid XML"):
            nmap.parse_nmap_xml("this is not xml")


class TestTheServiceEnumeration:
    """The operation, with the levels and the engines."""

    async def a_server(self):
        async def handler(reader, writer):
            await reader.read(100)
            writer.close()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        return server, server.sockets[0].getsockname()[1]

    async def test_the_native_scanner_finds_the_open_port(self, registry):
        server, port = await self.a_server()
        try:
            operation = registry.create("discovery.service.enumerate")
            response = await operation.run_request(
                {"host": "127.0.0.1", "ports": [port, 1]}
            )
            assert port in [entry["port"] for entry in response.open_ports]
            assert response.engine == "native"
            assert response.aggressiveness == "normal"
        finally:
            server.close()
            await server.wait_closed()

    async def test_the_level_is_reported(self, registry):
        server, port = await self.a_server()
        try:
            operation = registry.create("discovery.service.enumerate")
            response = await operation.run_request(
                {"host": "127.0.0.1", "ports": [port], "aggressiveness": "polite"}
            )
            assert response.aggressiveness == "polite"
        finally:
            server.close()
            await server.wait_closed()

    async def test_the_nmap_engine_is_used(self, registry, fake_runner, monkeypatch):
        monkeypatch.setattr("netforge.discovery.service.which", lambda program: "/usr/bin/nmap")
        from tests.conftest import result

        fake_runner.default = result(SAMPLE_XML)
        operation = registry.create("discovery.service.enumerate")
        context = ExecutionContext(command_runner=fake_runner)
        response = await operation.run_request(
            {"host": "10.0.0.1", "ports": [22, 80], "engine": "nmap"}, context
        )
        assert response.engine == "nmap"
        assert response.open_ports[0]["version"] == "OpenSSH 10.2p1"
        assert fake_runner.calls[0][0] == "nmap"

    async def test_the_nmap_engine_falls_back_when_nmap_is_absent(
        self, registry, fake_runner, monkeypatch
    ):
        monkeypatch.setattr("netforge.discovery.service.which", lambda program: None)
        server, port = await self.a_server()
        try:
            operation = registry.create("discovery.service.enumerate")
            response = await operation.run_request(
                {"host": "127.0.0.1", "ports": [port], "engine": "nmap"}
            )
            assert any("nmap is not installed" in warning for warning in response.warnings)
            assert port in [entry["port"] for entry in response.open_ports]
        finally:
            server.close()
            await server.wait_closed()


class TestThePortScanner:
    """The port scanner, with the levels and the engines."""

    async def test_the_nmap_engine_is_used(self, registry, fake_runner, monkeypatch):
        monkeypatch.setattr("netforge.security.scanner.which", lambda program: "/usr/bin/nmap")
        from tests.conftest import result

        fake_runner.default = result(SAMPLE_XML)
        operation = registry.create("security.portscan")
        context = ExecutionContext(command_runner=fake_runner)
        response = await operation.run_request(
            {"host": "10.0.0.1", "ports": [22, 80], "engine": "nmap"}, context
        )
        assert response.engine == "nmap"
        assert response.open_ports == [22, 80]
        assert response.results[0]["version"] == "OpenSSH 10.2p1"

    async def test_the_level_is_reported(self, registry, fake_runner, monkeypatch):
        monkeypatch.setattr("netforge.security.scanner.which", lambda program: None)
        operation = registry.create("security.portscan")
        response = await operation.run_request(
            {"host": "127.0.0.1", "ports": [1], "aggressiveness": "paranoid"}
        )
        assert response.aggressiveness == "paranoid"
