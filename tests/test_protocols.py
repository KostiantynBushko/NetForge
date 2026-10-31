"""The protocol implementations.

SNMP and Modbus are implemented in the framework, so their encodings are
tested here against the bytes the standards say they must be.
"""

from __future__ import annotations

import struct

import pytest

from netforge.protocols.base import ProtocolError
from netforge.protocols.modbus import (
    READ_HOLDING_REGISTERS,
    ModbusTcpClient,
)
from netforge.protocols.mqtt import MqttTopicFilter
from netforge.protocols.opcua import parse_endpoint
from netforge.protocols.snmp import (
    SNMP_ERRORS,
    decode_oid,
    encode_get_request,
    encode_oid,
    parse_get_response,
)


class TestOids:
    def test_an_oid_is_encoded(self):
        assert encode_oid("1.3.6.1.2.1.1.1.0") == bytes([0x2B, 0x06, 0x01, 0x02, 0x01, 0x01, 0x01, 0x00])

    def test_an_oid_round_trips(self):
        for oid in ("1.3.6.1.2.1.1.1.0", "1.3.6.1.4.1.9.9.13", "0.0"):
            assert decode_oid(encode_oid(oid)) == oid

    def test_an_invalid_oid_is_refused(self):
        with pytest.raises(ValueError):
            encode_oid("3.1.1")


class TestSnmpGet:
    def test_the_request_has_the_expected_shape(self):
        payload = encode_get_request("1.3.6.1.2.1.1.1.0", community="public", request_id=7)
        assert payload[0] == 0x30  # SEQUENCE
        # version 1 (v2c), community "public", then the GetRequest PDU.
        assert b"public" in payload
        assert 0xA0 in payload

    def test_a_response_is_parsed(self):
        # A GetResponse carrying sysDescr.0 with the value "Linux".
        value = b"Linux"
        varbind = bytes([0x30, 17]) + bytes([0x06, 0x08]) + bytes(
            [0x2B, 0x06, 0x01, 0x02, 0x01, 0x01, 0x01, 0x00]
        ) + bytes([0x04, len(value)]) + value
        varbinds = bytes([0x30, len(varbind)]) + varbind
        pdu_body = (
            bytes([0x02, 0x01, 0x07])  # request-id
            + bytes([0x02, 0x01, 0x00])  # error-status
            + bytes([0x02, 0x01, 0x00])  # error-index
            + varbinds
        )
        pdu = bytes([0xA2, len(pdu_body)]) + pdu_body
        body = bytes([0x02, 0x01, 0x01]) + bytes([0x04, 0x06]) + b"public" + pdu
        message = bytes([0x30, len(body)]) + body

        version, community, error_status, var_binds = parse_get_response(message)
        assert version == 1
        assert community == "public"
        assert error_status == 0
        assert len(var_binds) == 1
        assert var_binds[0].oid == "1.3.6.1.2.1.1.1.0"
        assert var_binds[0].text == "Linux"

    def test_the_error_status_of_the_agent_is_kept(self):
        # The same response, but the agent refused to answer: the error
        # status is 2, which is noSuchName.
        value = b"Linux"
        varbind = bytes([0x30, 17]) + bytes([0x06, 0x08]) + bytes(
            [0x2B, 0x06, 0x01, 0x02, 0x01, 0x01, 0x01, 0x00]
        ) + bytes([0x04, len(value)]) + value
        varbinds = bytes([0x30, len(varbind)]) + varbind
        pdu_body = (
            bytes([0x02, 0x01, 0x07])  # request-id
            + bytes([0x02, 0x01, 0x02])  # error-status: noSuchName
            + bytes([0x02, 0x01, 0x00])  # error-index
            + varbinds
        )
        pdu = bytes([0xA2, len(pdu_body)]) + pdu_body
        body = bytes([0x02, 0x01, 0x01]) + bytes([0x04, 0x06]) + b"public" + pdu
        message = bytes([0x30, len(body)]) + body

        _version, _community, error_status, _var_binds = parse_get_response(message)
        assert error_status == 2
        assert SNMP_ERRORS[error_status] == "noSuchName"

    def test_a_truncated_response_is_refused(self):
        with pytest.raises(ProtocolError):
            parse_get_response(bytes([0x30, 0x10, 0x02]))


class TestModbus:
    def test_a_frame_has_the_mbap_header(self):
        client = ModbusTcpClient("10.0.0.1")
        frame = client.build_frame(READ_HOLDING_REGISTERS, struct.pack("!HH", 0, 1))
        transaction_id, protocol_id, length, unit_id = struct.unpack_from("!HHHB", frame, 0)
        assert protocol_id == 0
        assert unit_id == 1
        assert length == len(frame) - 6
        assert frame[7] == READ_HOLDING_REGISTERS

    async def test_the_registers_are_read(self):
        async def handler(reader, writer):
            header = await reader.readexactly(7)
            _transaction, _protocol, length, _unit = struct.unpack("!HHHB", header)
            await reader.readexactly(length - 1)
            payload = struct.pack("!HH", 0x0100, 0x0200)
            response = (
                bytes([READ_HOLDING_REGISTERS, 0x04])
                + payload
            )
            writer.write(struct.pack("!HHHB", 1, 0, len(response) + 1, 1) + response)
            await writer.drain()
            writer.close()

        import asyncio

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            client = ModbusTcpClient("127.0.0.1", port)
            await client.connect()
            try:
                values = await client.read_holding_registers(0, 2)
            finally:
                await client.close()
            assert values == [0x0100, 0x0200]
        finally:
            server.close()
            await server.wait_closed()

    async def test_an_exception_is_raised_for_an_illegal_address(self):
        async def handler(reader, writer):
            header = await reader.readexactly(7)
            _transaction, _protocol, length, _unit = struct.unpack("!HHHB", header)
            await reader.readexactly(length - 1)
            response = bytes([READ_HOLDING_REGISTERS | 0x80, 0x02])  # illegal data address
            writer.write(struct.pack("!HHHB", 1, 0, len(response) + 1, 1) + response)
            await writer.drain()
            writer.close()

        import asyncio

        from netforge.protocols.modbus import ModbusException

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            client = ModbusTcpClient("127.0.0.1", port)
            await client.connect()
            try:
                with pytest.raises(ModbusException, match="illegalDataAddress"):
                    await client.read_holding_registers(0, 1)
            finally:
                await client.close()
        finally:
            server.close()
            await server.wait_closed()


class TestMqttTopics:
    @pytest.mark.parametrize(
        ("pattern", "topic", "expected"),
        [
            ("sensors/temperature", "sensors/temperature", True),
            ("sensors/temperature", "sensors/humidity", False),
            ("sensors/+", "sensors/temperature", True),
            ("sensors/+", "sensors/a/b", False),
            ("sensors/#", "sensors/a/b", True),
            ("sensors/#", "sensors", True),
            ("#", "anything/at/all", True),
            ("+/monitor", "host1/monitor", True),
        ],
    )
    def test_the_wildcards_follow_the_specification(self, pattern, topic, expected):
        assert MqttTopicFilter(pattern).matches(topic) is expected

    def test_a_hash_that_is_not_the_last_level_is_invalid(self):
        problems = MqttTopicFilter("a/#/b").validate()
        assert problems

    def test_a_wildcard_inside_a_level_is_invalid(self):
        problems = MqttTopicFilter("a/b+c").validate()
        assert problems

    def test_a_valid_filter_has_no_problems(self):
        assert MqttTopicFilter("a/+/b/#").validate() == []


class TestOpcUa:
    def test_an_endpoint_is_parsed(self):
        endpoint = parse_endpoint("opc.tcp://10.0.0.1:4840")
        assert endpoint.host == "10.0.0.1"
        assert endpoint.port == 4840
        assert endpoint.security_profile == "None (no encryption, no signing)"

    def test_a_secure_endpoint_is_recognised(self):
        endpoint = parse_endpoint("opc.tcps://host:4840")
        assert endpoint.security_profile == "Sign and Encrypt"
        assert endpoint.to_dict()["encrypted"] is True


class TestProtocolOperations:
    async def test_the_modbus_operation_reports_a_transport_failure(self, registry):
        operation = registry.create("protocols.modbus.read")
        response = await operation.run_request(
            {"host": "127.0.0.1", "port": 1, "timeout": 0.5}
        )
        assert response.values == []
        assert response.warnings

    async def test_the_mqtt_topic_operation_matches(self, registry):
        operation = registry.create("protocols.mqtt.topic.match")
        response = await operation.run_request(
            {"filters": ["sensors/#"], "topics": ["sensors/a", "other/b"]}
        )
        assert response.matches == [{"topic": "sensors/a", "filter": "sensors/#"}]
        assert response.unmatched_topics == ["other/b"]
