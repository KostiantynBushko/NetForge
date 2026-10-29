"""The security capability."""

from __future__ import annotations

import asyncio

import pytest

from netforge.security.headers import SECURITY_HEADERS, analyze_headers, analyze_set_cookie
from netforge.security.scanner import expand_ports, scan_port


class TestHeaderAnalysis:
    def test_a_missing_header_is_reported(self):
        findings = analyze_headers({})
        missing = [f for f in findings if not f.present and f.header in SECURITY_HEADERS]
        assert len(missing) == len(SECURITY_HEADERS)

    def test_a_present_header_is_reported_as_present(self):
        findings = analyze_headers({"Strict-Transport-Security": "max-age=31536000"})
        finding = next(f for f in findings if f.header == "strict-transport-security")
        assert finding.present is True
        assert finding.severity == "info"

    def test_the_header_names_are_matched_case_insensitively(self):
        findings = analyze_headers({"strict-transport-security": "max-age=1"})
        finding = next(f for f in findings if f.header == "strict-transport-security")
        assert finding.present is True

    def test_the_server_header_is_reported(self):
        findings = analyze_headers({"Server": "nginx/1.24.0"})
        finding = next(f for f in findings if f.header == "server")
        assert "nginx" in finding.message

    @pytest.mark.parametrize(
        ("cookie", "expected"),
        [
            ("a=1", "Secure"),
            ("a=1; Secure", "HttpOnly"),
            ("a=1; Secure; HttpOnly", "SameSite"),
        ],
    )
    def test_a_cookie_without_its_attributes_is_reported(self, cookie, expected):
        problems = analyze_set_cookie(cookie)
        assert any(expected in problem for problem in problems)

    def test_a_complete_cookie_has_no_problems(self):
        assert analyze_set_cookie("a=1; Secure; HttpOnly; SameSite=Strict") == []


class TestPortExpansion:
    def test_a_list_of_ports_is_kept(self):
        assert expand_ports([22, 80]) == [22, 80]

    def test_a_range_is_expanded(self):
        assert expand_ports("8000-8003") == [8000, 8001, 8002, 8003]

    def test_a_mixed_specification_is_expanded(self):
        assert expand_ports("22,80,443,8000-8001") == [22, 80, 443, 8000, 8001]

    def test_a_backwards_range_is_refused(self):
        with pytest.raises(ValueError):
            expand_ports("8003-8000")


class TestPortScan:
    async def test_an_open_port_is_found(self):
        async def handler(reader, writer):
            await reader.read(100)
            writer.close()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            result = await scan_port("127.0.0.1", port, timeout=2.0)
            assert result.state == "open"
            assert result.latency_ms is not None
        finally:
            server.close()
            await server.wait_closed()

    async def test_a_closed_port_is_found(self):
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        server.close()
        await server.wait_closed()

        result = await scan_port("127.0.0.1", port, timeout=2.0)
        assert result.state == "closed"


class TestSecurityOperations:
    async def test_the_port_scan_operation_reports_the_open_ports(self, registry):
        async def handler(reader, writer):
            await reader.read(100)
            writer.close()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            operation = registry.create("security.portscan")
            response = await operation.run_request({"host": "127.0.0.1", "ports": [port, 1]})
            assert port in response.open_ports
            assert response.scanned == 2
        finally:
            server.close()
            await server.wait_closed()

    async def test_the_header_analysis_operation_scores_the_response(self, registry):
        operation = registry.create("security.headers.analyze")
        response = await operation.run_request(
            {"headers": {"Strict-Transport-Security": "max-age=1"}}
        )
        assert response.checked == len(SECURITY_HEADERS)
        assert response.present == 1
        assert 0 < response.score < 100

    async def test_the_banner_operation_against_a_silent_port(self, registry):
        async def handler(reader, writer):
            await reader.read(100)
            writer.close()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            operation = registry.create("security.banner")
            response = await operation.run_request(
                {"host": "127.0.0.1", "port": port, "timeout": 0.5}
            )
            assert response.banner is None
        finally:
            server.close()
            await server.wait_closed()

    async def test_the_banner_operation_reads_a_greeting(self, registry):
        async def handler(reader, writer):
            writer.write(b"SSH-2.0-OpenSSH_9.6\r\n")
            await writer.drain()
            await reader.read(100)
            writer.close()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            operation = registry.create("security.banner")
            response = await operation.run_request(
                {"host": "127.0.0.1", "port": port, "timeout": 2.0}
            )
            assert response.banner is not None
            assert "OpenSSH" in response.banner
        finally:
            server.close()
            await server.wait_closed()
