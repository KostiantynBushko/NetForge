"""WebSocket connectivity.

A minimal RFC 6455 client, written on :mod:`asyncio` and the standard
library.  It speaks the part of the protocol that an operator actually
needs -- the handshake, text and binary frames, ping/pong and close -- and
nothing else: no extensions, no fragmentation across a message boundary
beyond reassembly of continuation frames.

It exists because a WebSocket endpoint is the transport behind a good deal
of live network telemetry, and requiring a third-party client library for it
would break the "one hard dependency" rule the framework set for itself.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import struct
from dataclasses import dataclass
from enum import IntEnum
from urllib.parse import urlparse

from netforge.connectivity.base import Connection, ConnectionState
from netforge.core.logging import get_logger

__all__ = ["WebSocketConnection", "WebSocketFrame", "WebSocketOpcode"]

_logger = get_logger("connectivity.websocket")

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WebSocketOpcode(IntEnum):
    """The RFC 6455 frame opcodes."""

    CONTINUATION = 0x0
    TEXT = 0x1
    BINARY = 0x2
    CLOSE = 0x8
    PING = 0x9
    PONG = 0xA


@dataclass(slots=True)
class WebSocketFrame:
    """One decoded WebSocket frame."""

    opcode: WebSocketOpcode
    payload: bytes
    fin: bool = True

    @property
    def text(self) -> str:
        """Return the payload decoded as UTF-8."""
        return self.payload.decode("utf-8", errors="replace")


class WebSocketConnection(Connection):
    """A WebSocket client connection."""

    def __init__(
        self,
        url: str,
        *,
        timeout: float | None = 30.0,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.url = url
        self.extra_headers = dict(extra_headers or {})
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._buffer = bytearray()

    # -- handshake ----------------------------------------------------------

    async def connect(self) -> None:
        """Perform the opening handshake."""
        if self.is_connected:
            return
        parsed = urlparse(self.url)
        if parsed.scheme not in ("ws", "wss"):
            raise ValueError(f"unsupported WebSocket scheme: {parsed.scheme!r}")
        if not parsed.hostname:
            raise ValueError(f"the URL {self.url!r} carries no host")

        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        self.state = ConnectionState.CONNECTING
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=self.timeout
            )
            if parsed.scheme == "wss":
                await self._upgrade_to_tls(host, port)
            await self._handshake(host, port, path)
        except Exception as exc:
            self._mark_failed(exc)
            await self.close()
            raise
        self.state = ConnectionState.CONNECTED

    async def _upgrade_to_tls(self, host: str, port: int) -> None:
        import ssl

        context = ssl.create_default_context()
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=context), timeout=self.timeout
        )

    async def _handshake(self, host: str, port: int, path: str) -> None:
        assert self._reader is not None and self._writer is not None
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        headers = {
            "Host": f"{host}:{port}" if port not in (80, 443) else host,
            "Upgrade": "websocket",
            "Connection": "Upgrade",
            "Sec-WebSocket-Key": key,
            "Sec-WebSocket-Version": "13",
            **self.extra_headers,
        }
        request = f"GET {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        request += "\r\n"
        self._writer.write(request.encode("ascii"))
        await self._writer.drain()

        status_line = await asyncio.wait_for(self._reader.readline(), timeout=self.timeout)
        if not status_line:
            raise ConnectionError("the server closed the connection during the handshake")
        parts = status_line.decode("latin-1").split(" ", 2)
        if len(parts) < 2 or parts[1] != "101":
            raise ConnectionError(f"the WebSocket handshake was refused: {status_line.decode().strip()}")

        response_headers: dict[str, str] = {}
        while True:
            line = await asyncio.wait_for(self._reader.readline(), timeout=self.timeout)
            if line in (b"\r\n", b"\n", b""):
                break
            name, _, value = line.decode("latin-1").partition(":")
            response_headers[name.strip().lower()] = value.strip()

        expected = base64.b64encode(
            hashlib.sha1((key + _GUID).encode("ascii")).digest()  # noqa: S324 - required by RFC 6455
        ).decode("ascii")
        if response_headers.get("sec-websocket-accept") != expected:
            raise ConnectionError("the server returned an invalid Sec-WebSocket-Accept header")

    # -- frames -------------------------------------------------------------

    async def send(self, payload: bytes | str, opcode: WebSocketOpcode = WebSocketOpcode.TEXT) -> None:
        """Send one frame."""
        if self._writer is None:
            raise ConnectionError("the connection is not open")
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        self._writer.write(_encode_frame(payload, opcode))
        await self._writer.drain()

    async def send_text(self, text: str) -> None:
        """Send a text frame."""
        await self.send(text, WebSocketOpcode.TEXT)

    async def send_ping(self, payload: bytes = b"") -> None:
        """Send a ping frame."""
        await self.send(payload, WebSocketOpcode.PING)

    async def send_close(self, code: int = 1000, reason: str = "") -> None:
        """Send a close frame."""
        await self.send(struct.pack("!H", code) + reason.encode("utf-8"), WebSocketOpcode.CLOSE)

    async def receive(self, *, timeout: float | None = None) -> WebSocketFrame:
        """Read one frame."""
        if self._reader is None:
            raise ConnectionError("the connection is not open")
        budget = self.timeout if timeout is None else timeout
        if budget is None:
            return await self._read_frame()
        return await asyncio.wait_for(self._read_frame(), timeout=budget)

    async def _read_frame(self) -> WebSocketFrame:
        assert self._reader is not None
        header = await self._reader.readexactly(2)
        first, second = header[0], header[1]
        fin = bool(first & 0x80)
        opcode = WebSocketOpcode(first & 0x0F)
        masked = bool(second & 0x80)
        length = second & 0x7F

        if length == 126:
            length = struct.unpack("!H", await self._reader.readexactly(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", await self._reader.readexactly(8))[0]

        mask = await self._reader.readexactly(4) if masked else b""
        payload = await self._reader.readexactly(length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))

        return WebSocketFrame(opcode=opcode, payload=payload, fin=fin)

    async def close(self) -> None:
        """Close the connection."""
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except (OSError, asyncio.TimeoutError):  # pragma: no cover - best effort
                pass
        self.state = ConnectionState.CLOSED


def _encode_frame(payload: bytes, opcode: WebSocketOpcode) -> bytes:
    """Encode a client frame.  A client frame is always masked."""
    header = bytearray()
    header.append(0x80 | int(opcode))
    length = len(payload)
    mask = os.urandom(4)
    if length < 126:
        header.append(0x80 | length)
    elif length < (1 << 16):
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
    header.extend(mask)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return bytes(header) + masked
