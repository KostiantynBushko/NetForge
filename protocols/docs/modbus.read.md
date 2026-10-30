# `protocols.modbus.read`

> Read holding registers or coils from a Modbus TCP server.

**Risk:** Safe (level 1)  
**Category:** protocols  
**Tags:** `coils`, `industrial`, `modbus`, `registers`  
**Implementation:** `netforge.protocols.modbus:ModbusTcpOperation`

---

## What it does

Reads holding registers (function code 3) or coils (function code 1) from a Modbus TCP server. The read changes nothing on the server, so the operation is declared at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `host` | string | — | **Required.** The Modbus server. (at least 1 character) |
| `address` | integer | `0` | The first register or coil. (at least 0, at most 65535) |
| `count` | integer | `1` | How many registers or coils to read. (at least 1, at most 125) |
| `function` | string | `"holding"` | 'holding' or 'coils'. |
| `unit_id` | integer | `1` | The unit identifier of the server. (at least 0, at most 255) |
| `port` | integer | `502` | The TCP port of the server. (at least 1, at most 65535) |
| `timeout` | number | `10.0` | Timeout in seconds. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `host` | string | The server that was read. |
| `function` | string | The Modbus function code that was used. |
| `address` | integer | The first register or coil that was read. |
| `count` | integer | How many registers or coils were read. |
| `values` | list of integer | The values that were read. |
| `coils` | list of boolean | The coils that were read. |

## Using it

### From the command line

```console
$ netforge run protocols.modbus.read --host <string>
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("protocols.modbus.read")
result = await operation.run(host=...)
```

## How it works

Modbus TCP.

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

## See also

* [the `protocols` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
