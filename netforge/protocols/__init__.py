"""Protocol implementations.

Each protocol in this package has a small, uniform shape: a client class
that speaks the wire protocol, and -- where it makes sense -- an operation
that exposes it.

The protocols that need a third-party client (MQTT via ``paho-mqtt``,
OPC UA via ``asyncua``) import it lazily and report a clear error when it
is missing.  The protocols that are simple enough to implement directly --
HTTP, SNMP, Modbus TCP -- are implemented here, on the standard library
alone.
"""

from __future__ import annotations

from netforge.protocols.base import ProtocolAdapter, ProtocolError
from netforge.protocols.http import HttpProtocol, HttpProtocolOperation
from netforge.protocols.modbus import ModbusTcpClient, ModbusTcpOperation
from netforge.protocols.mqtt import MqttTopicFilter, MqttTopicOperation
from netforge.protocols.opcua import OpcUaEndpoint, OpcUaOperation
from netforge.protocols.snmp import SnmpClient, SnmpGetOperation

__all__ = [
    "HttpProtocol",
    "HttpProtocolOperation",
    "ModbusTcpClient",
    "ModbusTcpOperation",
    "MqttTopicFilter",
    "MqttTopicOperation",
    "OpcUaEndpoint",
    "OpcUaOperation",
    "ProtocolAdapter",
    "ProtocolError",
    "SnmpClient",
    "SnmpGetOperation",
]
