"""SNMP.

An SNMP v1/v2c GET, implemented directly on BER (ASN.1 distinguished
encoding rules).  SNMP needs no cryptography to be *read*, and the BER
encoding of a GET request is small enough to be worth having in the
framework rather than pulling in a library for it.

The message structure is::

    Message ::= SEQUENCE {
        version   INTEGER,          -- 0 for v1, 1 for v2c
        community OCTET STRING,
        pdu       GetRequest-PDU
    }

    GetRequest-PDU ::= [0] IMPLICIT SEQUENCE {
        request-id   INTEGER,
        error-status INTEGER,
        error-index  INTEGER,
        variable-bindings SEQUENCE OF VarBind
    }

    VarBind ::= SEQUENCE { name OBJECT IDENTIFIER, value ANY }

SNMP v3 is *not* implemented: it needs USM (user-based security), which
means key derivation and a message-digest algorithm.  The operation says so
rather than pretending otherwise.
"""

from __future__ import annotations

import asyncio
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
    "SnmpClient",
    "SnmpGetOperation",
    "SnmpVarBind",
    "encode_oid",
    "encode_get_request",
    "parse_get_response",
    "SNMP_ERRORS",
]

_logger = get_logger("protocols.snmp")

#: The SNMPv2c error-status values and their names.
SNMP_ERRORS: dict[int, str] = {
    0: "noError",
    1: "tooBig",
    2: "noSuchName",
    3: "badValue",
    4: "readOnly",
    5: "genErr",
    6: "noAccess",
    7: "wrongType",
    8: "wrongLength",
    9: "wrongEncoding",
    10: "wrongValue",
    11: "noCreation",
    12: "inconsistentValue",
    13: "resourceUnavailable",
    14: "commitFailed",
    15: "undoFailed",
    16: "authorizationError",
    17: "notWritable",
    18: "inconsistentName",
}


def encode_oid(oid: str) -> bytes:
    """Encode a dotted OID into its BER content bytes.

    The first two arcs are packed into a single byte, because the first arc
    is 0, 1 or 2 and the second arc is 0..39 when the first is 0 or 1.
    """
    parts = [int(part) for part in oid.strip().strip(".").split(".")]
    if len(parts) < 2:
        raise ValueError(f"{oid!r} is not a valid OID")

    first, second = parts[0], parts[1]
    if first > 2 or (first < 2 and second > 39):
        raise ValueError(f"{oid!r} is not a valid OID")

    body = bytearray([first * 40 + second])
    for arc in parts[2:]:
        if arc < 0:
            raise ValueError(f"{oid!r} is not a valid OID")
        chunk = bytearray()
        chunk.append(arc & 0x7F)
        arc >>= 7
        while arc:
            chunk.append((arc & 0x7F) | 0x80)
            arc >>= 7
        body.extend(reversed(chunk))
    return bytes(body)


def decode_oid(data: bytes) -> str:
    """Decode BER content bytes back into a dotted OID."""
    if not data:
        raise ProtocolError("the OID is empty")
    first = data[0]
    arcs = [first // 40, first % 40]
    value = 0
    for byte in data[1:]:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            arcs.append(value)
            value = 0
    return ".".join(str(arc) for arc in arcs)


def _ber_length(length: int) -> bytes:
    """Encode a BER length."""
    if length < 0x80:
        return bytes([length])
    encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(encoded)]) + encoded


def _ber(tag: int, content: bytes) -> bytes:
    """Encode a BER TLV."""
    return bytes([tag]) + _ber_length(len(content)) + content


def _ber_integer(value: int) -> bytes:
    """Encode a BER INTEGER."""
    length = max(1, (value.bit_length() + 8) // 8)
    return _ber(0x02, value.to_bytes(length, "big", signed=True))


def _ber_octet_string(value: str) -> bytes:
    """Encode a BER OCTET STRING."""
    return _ber(0x04, value.encode("utf-8"))


def _ber_oid(oid: str) -> bytes:
    """Encode a BER OBJECT IDENTIFIER."""
    return _ber(0x06, encode_oid(oid))


def _ber_null() -> bytes:
    """Encode a BER NULL."""
    return _ber(0x05, b"")


def _ber_sequence(*parts: bytes) -> bytes:
    """Encode a BER SEQUENCE."""
    return _ber(0x30, b"".join(parts))


def encode_get_request(oid: str, *, community: str = "public", version: int = 1, request_id: int = 1) -> bytes:
    """Encode an SNMP GET request for one OID."""
    varbind = _ber_sequence(_ber_oid(oid), _ber_null())
    pdu = _ber(
        0xA0,
        _ber_integer(request_id)
        + _ber_integer(0)  # error-status
        + _ber_integer(0)  # error-index
        + _ber_sequence(varbind),
    )
    return _ber_sequence(_ber_integer(version), _ber_octet_string(community), pdu)


def _read_tlv(data: bytes, offset: int) -> tuple[int, bytes, int]:
    """Read one BER TLV; return ``(tag, content, next_offset)``."""
    if offset >= len(data):
        raise ProtocolError("the message ended unexpectedly")
    tag = data[offset]
    offset += 1
    if offset >= len(data):
        raise ProtocolError("the message ended unexpectedly")
    first = data[offset]
    offset += 1
    if first < 0x80:
        length = first
    else:
        count = first & 0x7F
        if count == 0 or offset + count > len(data):
            raise ProtocolError("the message carries an invalid length")
        length = int.from_bytes(data[offset : offset + count], "big")
        offset += count
    if offset + length > len(data):
        raise ProtocolError("the message ended unexpectedly")
    return tag, data[offset : offset + length], offset + length


@dataclass(slots=True)
class SnmpVarBind:
    """One variable binding of an SNMP response."""

    oid: str
    value: bytes
    value_type: str = ""

    @property
    def text(self) -> str:
        """Return the value decoded as text, with the NUL terminator removed."""
        return self.value.decode("utf-8", errors="replace").rstrip("\x00")

    @property
    def as_int(self) -> int | None:
        """Return the value as an integer, when it is one."""
        try:
            return int.from_bytes(self.value, "big", signed=False)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None


def parse_get_response(data: bytes) -> tuple[int, str, int, list[SnmpVarBind]]:
    """Parse an SNMP response.

    Returns ``(version, community, error_status, var_binds)``.  The error
    status is the one the agent reported: zero is ``noError``, and
    anything else names a failure the agent refused to answer.
    """
    tag, content, _ = _read_tlv(data, 0)
    if tag != 0x30:
        raise ProtocolError(f"expected a SEQUENCE, got the tag 0x{tag:02x}")

    offset = 0
    tag, version_bytes, offset = _read_tlv(content, offset)
    if tag != 0x02:
        raise ProtocolError("the message does not start with a version")
    version = int.from_bytes(version_bytes, "big", signed=True)

    tag, community_bytes, offset = _read_tlv(content, offset)
    if tag != 0x04:
        raise ProtocolError("the message does not carry a community string")
    community = community_bytes.decode("utf-8", errors="replace")

    tag, pdu, offset = _read_tlv(content, offset)
    if tag not in (0xA1, 0xA2):  # GetResponse, GetNextResponse
        raise ProtocolError(f"expected a response PDU, got the tag 0x{tag:02x}")

    inner = 0
    tag, request_id_bytes, inner = _read_tlv(pdu, inner)
    tag, error_status_bytes, inner = _read_tlv(pdu, inner)
    error_status = int.from_bytes(error_status_bytes, "big", signed=True)
    tag, _error_index_bytes, inner = _read_tlv(pdu, inner)

    tag, varbinds_content, inner = _read_tlv(pdu, inner)
    var_binds: list[SnmpVarBind] = []
    position = 0
    while position < len(varbinds_content):
        tag, varbind_content, position = _read_tlv(varbinds_content, position)
        inner_position = 0
        _tag, oid_bytes, inner_position = _read_tlv(varbind_content, inner_position)
        _tag, value_bytes, inner_position = _read_tlv(varbind_content, inner_position)
        var_binds.append(
            SnmpVarBind(
                oid=decode_oid(oid_bytes),
                value=value_bytes,
                value_type=_value_type_name(value_bytes),
            )
        )

    return version, community, error_status, var_binds


def _value_type_name(value: bytes) -> str:
    """Return the name of the ASN.1 type the value looks like."""
    if not value:
        return "null"
    if len(value) == 1 and value[0] in (0x02, 0x04, 0x05, 0x06, 0x40, 0x41, 0x42, 0x43, 0x44, 0x46):
        return {
            0x02: "integer",
            0x04: "octet-string",
            0x05: "null",
            0x06: "oid",
            0x40: "ip-address",
            0x41: "counter",
            0x42: "gauge",
            0x43: "timeticks",
            0x44: "opaque",
            0x46: "counter64",
        }[value[0]]
    return "raw"


class SnmpClient:
    """A minimal SNMP v1/v2c client."""

    def __init__(
        self,
        host: str,
        port: int = 161,
        *,
        community: str = "public",
        version: int = 1,
        timeout: float | None = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.community = community
        self.version = version
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_id = 0

    async def connect(self) -> None:
        """Open the UDP session."""
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=self.timeout,
        )

    async def close(self) -> None:
        """Close the UDP session."""
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (TimeoutError, OSError):  # pragma: no cover - best effort
                pass

    async def get(self, oid: str) -> tuple[int, str, int, list[SnmpVarBind]]:
        """Perform a GET for one OID and return the parsed response."""
        if self._writer is None:
            raise ProtocolError("the SNMP session is not open")
        self._request_id = (self._request_id + 1) % 0x7FFFFFFF
        payload = encode_get_request(
            oid, community=self.community, version=self.version, request_id=self._request_id
        )
        self._writer.write(payload)
        await self._writer.drain()
        data = await asyncio.wait_for(self._reader.read(65535), timeout=self.timeout)
        if not data:
            raise ProtocolError("the agent did not answer")
        return parse_get_response(data)


class SnmpGetRequest(RequestModel):
    """Request of :class:`SnmpGetOperation`."""

    host: str = Field(min_length=1, description="The agent to query.")
    oid: str = Field(min_length=1, description="The OID to read.")
    port: int = Field(default=161, ge=1, le=65535, description="The agent's UDP port.")
    community: str = Field(default="public", description="The community string.")
    version: int = Field(default=1, ge=0, le=1, description="0 for SNMPv1, 1 for SNMPv2c.")
    timeout: float | None = Field(default=10.0, gt=0.0, description="Timeout in seconds.")


class SnmpGetResponse(ResponseModel):
    """Response of :class:`SnmpGetOperation`."""

    host: str = Field(description="The agent that was queried.")
    oid: str = Field(description="The OID that was read.")
    error_status: int = Field(default=0, description="The error status of the response.")
    error_name: str = Field(default="noError", description="The name of the error status.")
    values: list[dict[str, object]] = Field(default_factory=list, description="The values that came back.")


class SnmpGetOperation(Operation[SnmpGetRequest, SnmpGetResponse]):
    """Read one OID from an SNMP agent."""

    name = "protocols.snmp.get"
    category = CapabilityCategory.PROTOCOLS
    risk_level = RiskLevel.SAFE
    summary = "Read a single OID from an SNMP agent."
    description = (
        "Performs an SNMP GET against an agent and returns the value of the OID. "
        "SNMPv1 and SNMPv2c are supported; SNMPv3 is not, and the operation says so "
        "rather than failing obscurely."
    )
    tags = frozenset({"snmp", "oid", "get", "agent"})

    request_model = SnmpGetRequest
    response_model = SnmpGetResponse

    async def execute(
        self, request: SnmpGetRequest, context: ExecutionContext
    ) -> SnmpGetResponse:
        """Read the OID."""
        client = SnmpClient(
            request.host,
            request.port,
            community=request.community,
            version=request.version,
            timeout=request.timeout,
        )
        started = time.perf_counter()
        try:
            await client.connect()
            _version, _community, error_status, var_binds = await client.get(request.oid)
        except (TimeoutError, OSError, ProtocolError) as exc:
            return SnmpGetResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                host=request.host,
                oid=request.oid,
                error_status=-1,
                error_name="transportError",
                values=[],
                warnings=[str(exc)],
            )
        finally:
            await client.close()

        values = [
            {
                "oid": bind.oid,
                "value": bind.text,
                "type": bind.value_type,
                "raw": bind.value.hex(),
            }
            for bind in var_binds
        ]
        return SnmpGetResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            host=request.host,
            oid=request.oid,
            error_status=error_status,
            error_name=SNMP_ERRORS.get(error_status, "unknownError"),
            values=values,
        )
