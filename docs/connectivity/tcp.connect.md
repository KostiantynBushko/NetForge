# `connectivity.tcp.connect`

> Open a TCP connection to a host and port and report whether it succeeded.

**Risk:** Safe (level 1)  
**Category:** connectivity  
**Tags:** `probe`, `reachability`, `tcp`  
**Implementation:** `netforge.connectivity.tcp:TcpConnectOperation`

---

## What it does

Attempts a TCP connection to the given host and port and reports reachability, the time it took and the addresses involved. The connection is closed immediately afterwards; no data is sent.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `host` | string | — | **Required.** The host to connect to. |
| `port` | integer | — | **Required.** The TCP port to connect to. (at least 1, at most 65535) |
| `timeout` | number | — | Connect timeout in seconds. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `host` | string | The host that was reached. |
| `port` | integer | The port that was reached. |
| `reachable` | boolean | Whether the connection succeeded. |
| `latency_ms` | number | How long the connection took, in milliseconds. |
| `local_address` | string | The address the connection was made from. |
| `peer_address` | string | The address of the other end. |
| `error` | string | Why the connection failed, when it did. |

## Using it

### From the command line

```console
$ netforge run connectivity.tcp.connect --host <string> --port <integer>
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("connectivity.tcp.connect")
result = await operation.run(host=..., port=...)
```

## How it works

TCP connectivity.

A TCP connection is the simplest useful thing NetForge can do to a remote
host, and it is the substrate several other capabilities are built on: the
port scanner, the banner grabber, the proxy and the Modbus client all speak
TCP.

The ``TcpConnectOperation`` exposes the plain reachability check as an
operation, because "can I open a TCP session to this host and port" is a
question an operator and an agent both ask constantly.

## See also

* [the `connectivity` package](README.md) — every operation it publishes
* [the architecture](../ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../README.md)
