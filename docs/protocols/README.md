# `netforge.protocols`

Each protocol in this package has a small, uniform shape: a client class
that speaks the wire protocol, and — where it makes sense — an operation
that exposes it.

The protocols that need a third-party client (MQTT via `paho-mqtt`, OPC UA
via `asyncua`) import it lazily and report a clear error when it is
missing. The protocols that are simple enough to implement directly — HTTP,
SNMP, Modbus TCP — are implemented here, on the standard library alone.

---

## Operations

<!-- generated:operations -->
| Operation | Risk | What it does |
|---|---|---|
| [`protocols.http.request`](http.request.md) | Safe | Speak the HTTP protocol against an endpoint and report the reply. |
| [`protocols.modbus.read`](modbus.read.md) | Safe | Read holding registers or coils from a Modbus TCP server. |
| [`protocols.mqtt.topic.match`](mqtt.topic.match.md) | Safe | Match MQTT topics against wildcard filters. |
| [`protocols.opcua.endpoint`](opcua.endpoint.md) | Safe | Describe an OPC UA endpoint and optionally open a session. |
| [`protocols.snmp.get`](snmp.get.md) | Safe | Read a single OID from an SNMP agent. |
<!-- /generated:operations -->

---

## The base

`ProtocolAdapter(host, port=None, *, timeout=30.0)` is the base class of
every protocol client. `ProtocolError` is raised when an exchange fails.

---

## HTTP

`HttpProtocol(host, port=None, *, timeout=30.0, scheme='http', path='/',
verify_tls=True, user_agent='netforge/0.1.0')` is an HTTP client expressed
as a protocol adapter — the same wire behaviour as the transport in
[connectivity.md](../connectivity/README.md), but with the protocol adapter's shape.

---

## SNMP

`SnmpClient(host, port=161, *, community='public', version=1,
timeout=10.0)` is a minimal SNMP v1/v2c client, implemented directly on
the standard library.

SNMPv3 is not implemented: it needs USM — key derivation and message
digests — and the specification says so explicitly. v1 and v2c are.

---

## Modbus TCP

`ModbusTcpClient(host, port=502, *, unit_id=1, timeout=10.0)` is a Modbus
TCP client. `ModbusTcpOperation` reads holding registers or coils.

---

## MQTT

`MqttTopicFilter(pattern)` is an MQTT topic filter, and the operation
matches topics against wildcard filters.

The broker session is not implemented — it needs a client library, and
`paho-mqtt` is the optional extra. The *topic matcher*, which is the part
worth having exactly right and which can be tested offline, is.

---

## OPC UA

`OpcUaEndpoint(url, scheme, host, port, path, security_profile)` is a
parsed OPC UA endpoint. The operation describes an endpoint and can
optionally open a session.

The binary protocol needs a client library; `asyncua` is the optional
extra. The endpoint *parser* is implemented.

---

## Using it

```python
from netforge.protocols import MqttTopicFilter

filter = MqttTopicFilter("devices/+/temperature")
filter.matches("devices/kitchen/temperature")   # True
```

Through the framework:

```python
operation = registry.create("protocols.snmp.get")
result = await operation.run(host="10.0.0.1", oid="1.3.6.1.2.1.1.1.0")
```

---

## The public API

<!-- generated:public-api -->
```text
class HttpProtocol(host: str, port: int | None = None, *, timeout: float | None = 30.0, scheme: str = 'http', path: str = '/', verify_tls: bool = True, user_agent: str = 'netforge/0.1.0')
class HttpProtocolOperation()
class ModbusTcpClient(host: str, port: int = 502, *, unit_id: int = 1, timeout: float | None = 10.0)
class ModbusTcpOperation()
class MqttTopicFilter(pattern: str)
class MqttTopicOperation()
class OpcUaEndpoint(url: str, scheme: str, host: str, port: int | None, path: str, security_profile: str)
class OpcUaOperation()
class ProtocolAdapter(host: str, port: int | None = None, *, timeout: float | None = 30.0)
class ProtocolError(args, kwargs)
class SnmpClient(host: str, port: int = 161, *, community: str = 'public', version: int = 1, timeout: float | None = 10.0)
class SnmpGetOperation()
```
<!-- /generated:public-api -->

---

## Notes

* The optional clients are imported inside the method that needs them, so
  `netforge.protocols` imports cleanly with no extras installed.
* `community='public'` is the SNMP default and is the least safe value —
  set it explicitly for anything but a lab network.
* See also: [the architecture](../ARCHITECTURE.md#what-is-deliberately-not-implemented),
  [connectivity.md](../connectivity/README.md).
