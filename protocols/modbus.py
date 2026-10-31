"""Modbus TCP.

Modbus TCP is one of the simplest industrial protocols: a six-byte MBAP
header, a one-byte function code and a small payload.  It is implemented
here on the standard library.

The frame is::

    MBAP header
      transaction identifier  2 bytes
      protocol identifier     2 bytes   (always 0)
      length                  2 bytes   (the length of the rest)
      unit identifier         1 byte

    PDU
      function code           1 byte
      data                    n bytes

Reading holding registers (function code 3) and reading coils (function
code 1) are the two requests that are implemented here.
"""

from __future__ import annotations

import asyncio
import struct
import time
from dataclasses import dataclass

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel
from netforge.protocols.base import ProtocolError

__all__ = [
    "ModbusTcpClient",
    "ModbusTcpOperation",
    "ModbusException",
    "MODBUS_EXCEPTIONS",
    "READ_COILS",
    "READ_HOLDING_REGISTERS",
]

_logger = get_logger("protocols.modbus")

READ_COILS = 0x01
READ_INPUT_CONTACTS = 0x02
READ_HOLDING_REGISTERS = 0x03
READ_INPUT_REGISTERS = 0x04
WRITE_SINGLE_REGISTER = 0x06
WRITE_MULTIPLE_REGISTERS = 0x10

#: The Modbus exception codes and their names.
MODBUS_EXCEPTIONS: dict[int, str] = {
    0x01: "illegalFunction",
    0x02: "illegalDataAddress",
    0x03: "illegalDataValue",
    0x04: "serverDeviceFailure",
    0x05: "acknowledge",
    0x06: "serverDeviceBusy",
    0x08: "memoryParityError",
    0x0A: "gatewayPathUnavailable",
    0x0B: "gatewayTargetDeviceFailedToRespond",
}


class ModbusException(ProtocolError):
    """The Modbus server answered with an exception."""


@dataclass(slots=True)
class ModbusFrame:
    """A decoded Modbus TCP frame."""

    transaction_id: int
    unit_id: int
    function_code: int
    data: bytes

    @property
    def is_exception(self) -> bool:
        """Return ``True`` when the frame carries an exception code."""
        return self.function_code & 0x80 == 0x80

    @property
    def exception_code(self) -> int | None:
        """Return the exception code, when the frame carries one."""
        return self.data[0] if self.is_exception and self.data else None

    @property
    def exception_name(self) -> str | None:
        """Return the name of the exception, when the frame carries one."""
        code = self.exception_code
        return MODBUS_EXCEPTIONS.get(code) if code is not None else None


class ModbusTcpClient:
    """A Modbus TCP client."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        *,
        unit_id: int = 1,
        timeout: float | None = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._transaction_id = 0

    async def connect(self) -> None:
        """Open the TCP session."""
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=self.timeout
        )

    async def close(self) -> None:
        """Close the TCP session."""
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (TimeoutError, OSError):  # pragma: no cover - best effort
                pass

    def build_frame(self, function_code: int, data: bytes) -> bytes:
        """Build a complete Modbus TCP frame."""
        self._transaction_id = (self._transaction_id + 1) % 0xFFFF
        pdu = bytes([function_code]) + data
        header = struct.pack("!HHHB", self._transaction_id, 0, len(pdu) + 1, self.unit_id)
        return header + pdu

    async def request(self, function_code: int, data: bytes) -> ModbusFrame:
        """Send a request and read the answer."""
        if self._writer is None or self._reader is None:
            raise ProtocolError("the Modbus session is not open")
        self._writer.write(self.build_frame(function_code, data))
        await self._writer.drain()

        header = await asyncio.wait_for(self._reader.readexactly(7), timeout=self.timeout)
        transaction_id, protocol_id, length, unit_id = struct.unpack("!HHHB", header)
        if protocol_id != 0:
            raise ProtocolError(f"the server answered with the protocol identifier {protocol_id}")
        body = await asyncio.wait_for(self._reader.readexactly(max(0, length - 1)), timeout=self.timeout)
        if not body:
            raise ProtocolError("the server sent an empty response")
        return ModbusFrame(
            transaction_id=transaction_id,
            unit_id=unit_id,
            function_code=body[0],
            data=body[1:],
        )

    async def read_holding_registers(
        self, address: int, count: int = 1
    ) -> list[int]:
        """Read holding registers (function code 3)."""
        frame = await self.request(READ_HOLDING_REGISTERS, struct.pack("!HH", address, count))
        if frame.is_exception:
            raise ModbusException(
                f"the server answered with the exception {frame.exception_name} "
                f"({frame.exception_code})"
            )
        if len(frame.data) < 2:
            raise ProtocolError("the response is too short")
        # frame.data starts at the byte count: the function code was consumed
        # when the frame was decoded.
        byte_count = frame.data[0]
        payload = frame.data[1 : 1 + byte_count]
        return [
            int.from_bytes(payload[index : index + 2], "big")
            for index in range(0, len(payload) - 1, 2)
        ]

    async def read_coils(self, address: int, count: int = 1) -> list[bool]:
        """Read coils (function code 1)."""
        frame = await self.request(READ_COILS, struct.pack("!HH", address, count))
        if frame.is_exception:
            raise ModbusException(
                f"the server answered with the exception {frame.exception_name} "
                f"({frame.exception_code})"
            )
        if len(frame.data) < 2:
            raise ProtocolError("the response is too short")
        byte_count = frame.data[0]
        payload = frame.data[1 : 1 + byte_count]
        bits: list[bool] = []
        for byte in payload:
            for bit in range(8):
                bits.append(bool(byte & (1 << bit)))
        return bits[:count]


class ModbusTcpRequest(RequestModel):
    """Request of :class:`ModbusTcpOperation`."""

    host: str = Field(min_length=1, description="The Modbus server.")
    address: int = Field(default=0, ge=0, le=0xFFFF, description="The first register or coil.")
    count: int = Field(default=1, ge=1, le=125, description="How many registers or coils to read.")
    function: str = Field(default="holding", description="'holding' or 'coils'.")
    unit_id: int = Field(default=1, ge=0, le=255, description="The unit identifier of the server.")
    port: int = Field(default=502, ge=1, le=65535, description="The TCP port of the server.")
    timeout: float | None = Field(default=10.0, gt=0.0, description="Timeout in seconds.")


class ModbusTcpResponse(ResponseModel):
    """Response of :class:`ModbusTcpOperation`."""

    host: str = Field(description="The server that was read.")
    function: str = Field(description="The Modbus function code that was used.")
    address: int = Field(description="The first register or coil that was read.")
    count: int = Field(description="How many registers or coils were read.")
    values: list[int] = Field(default_factory=list, description="The values that were read.")
    coils: list[bool] = Field(default_factory=list, description="The coils that were read.")


class ModbusTcpOperation(Operation[ModbusTcpRequest, ModbusTcpResponse]):
    """Read registers or coils from a Modbus TCP server."""

    name = "protocols.modbus.read"
    category = CapabilityCategory.PROTOCOLS
    risk_level = RiskLevel.SAFE
    summary = "Read holding registers or coils from a Modbus TCP server."
    description = (
        "Reads holding registers (function code 3) or coils (function code 1) from a "
        "Modbus TCP server. The read changes nothing on the server, so the operation "
        "is declared at the safe level."
    )
    tags = frozenset({"modbus", "industrial", "registers", "coils"})

    request_model = ModbusTcpRequest
    response_model = ModbusTcpResponse

    async def execute(
        self, request: ModbusTcpRequest, context: ExecutionContext
    ) -> ModbusTcpResponse:
        """Perform the read."""
        client = ModbusTcpClient(
            request.host, request.port, unit_id=request.unit_id, timeout=request.timeout
        )
        started = time.perf_counter()
        try:
            await client.connect()
            if request.function.lower() in {"coil", "coils"}:
                coils = await client.read_coils(request.address, request.count)
                values: list[int] = []
            else:
                values = await client.read_holding_registers(request.address, request.count)
                coils = []
        except (TimeoutError, OSError, ProtocolError) as exc:
            return ModbusTcpResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                host=request.host,
                function=request.function,
                address=request.address,
                count=request.count,
                warnings=[str(exc)],
            )
        finally:
            await client.close()

        return ModbusTcpResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            host=request.host,
            function=request.function,
            address=request.address,
            count=request.count,
            values=values,
            coils=coils,
        )
