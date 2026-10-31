"""The connectivity layer."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import struct

import pytest

from netforge.connectivity.tcp import TcpConnection
from netforge.connectivity.websocket import WebSocketConnection, WebSocketOpcode, _encode_frame

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class TestTcpConnection:
    async def test_a_connection_is_opened_and_closed(self):
        async def handler(reader, writer):
            writer.write(b"hello")
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            connection = TcpConnection("127.0.0.1", port, timeout=2.0)
            await connection.connect()
            assert connection.is_connected
            data = await connection.read(5)
            assert data == b"hello"
            await connection.close()
            assert not connection.is_connected
        finally:
            server.close()
            await server.wait_closed()

    async def test_a_closed_port_fails(self):
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        server.close()
        await server.wait_closed()

        connection = TcpConnection("127.0.0.1", port, timeout=1.0)
        with pytest.raises((OSError, asyncio.TimeoutError)):
            await connection.connect()

    async def test_the_operation_reports_a_reachable_port(self, registry):
        async def handler(reader, writer):
            await reader.read(10)
            writer.close()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            operation = registry.create("connectivity.tcp.connect")
            response = await operation.run_request({"host": "127.0.0.1", "port": port})
            assert response.reachable is True
            assert response.latency_ms is not None
        finally:
            server.close()
            await server.wait_closed()

    async def test_the_operation_reports_an_unreachable_port(self, registry):
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        server.close()
        await server.wait_closed()

        operation = registry.create("connectivity.tcp.connect")
        response = await operation.run_request({"host": "127.0.0.1", "port": port, "timeout": 1.0})
        assert response.reachable is False
        assert response.error


class TestWebSocketFraming:
    def test_a_short_frame_is_encoded(self):
        frame = _encode_frame(b"hi", WebSocketOpcode.TEXT)
        assert frame[0] == 0x81  # FIN + text
        assert frame[1] & 0x80  # masked
        assert frame[1] & 0x7F == 2

    def test_a_long_frame_uses_the_extended_length(self):
        payload = b"x" * 200
        frame = _encode_frame(payload, WebSocketOpcode.BINARY)
        assert frame[1] & 0x7F == 126
        assert struct.unpack_from("!H", frame, 2)[0] == 200

    def test_the_payload_is_masked(self):
        frame = _encode_frame(b"ABCD", WebSocketOpcode.TEXT)
        mask = frame[2:6]
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(frame[6:]))
        assert payload == b"ABCD"


class TestWebSocketHandshake:
    async def test_the_handshake_and_a_text_frame(self):
        async def handler(reader, writer):
            request = b""
            while b"\r\n\r\n" not in request:
                request += await reader.read(1024)
            key = ""
            for line in request.decode("latin-1").split("\r\n"):
                if line.lower().startswith("sec-websocket-key:"):
                    key = line.split(":", 1)[1].strip()
            accept = base64.b64encode(
                hashlib.sha1((key + _GUID).encode("ascii")).digest()
            ).decode("ascii")
            writer.write(
                (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
                ).encode("latin-1")
            )
            await writer.drain()

            # Read one masked client frame and answer with an unmasked text frame.
            header = await reader.readexactly(2)
            length = header[1] & 0x7F
            await reader.readexactly(4)
            await reader.readexactly(length)
            writer.write(bytes([0x81, 0x05]) + b"hello")
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            connection = WebSocketConnection(f"ws://127.0.0.1:{port}/socket", timeout=5.0)
            await connection.connect()
            assert connection.is_connected
            await connection.send_text("ping")
            frame = await connection.receive(timeout=5.0)
            assert frame.opcode == WebSocketOpcode.TEXT
            assert frame.text == "hello"
            await connection.close()
        finally:
            server.close()
            await server.wait_closed()
