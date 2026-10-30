# `protocols.opcua.endpoint`

> Describe an OPC UA endpoint and optionally open a session.

**Risk:** Safe (level 1)  
**Category:** protocols  
**Tags:** `endpoint`, `industrial`, `opcua`  
**Implementation:** `netforge.protocols.opcua:OpcUaOperation`

---

## What it does

Parses an OPC UA endpoint URL and reports the transport, the port and the security profile it implies. With connect set, a session is opened as well, which needs the optional asyncua extra.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `url` | string | — | **Required.** The OPC UA endpoint URL. (at least 1 character) |
| `connect` | boolean | `false` | Also try to open a session. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `url` | string | The endpoint that was described. |
| `endpoint` | object | The endpoint as the server reported it. |
| `connected` | boolean | Whether a session was opened. |
| `nodes` | list of string | The nodes of the endpoint. |

## Using it

### From the command line

```console
$ netforge run protocols.opcua.endpoint --url "..."
```

The values above are placeholders.  The request may also be given as a JSON object, which the flags are laid over:

```console
$ netforge run protocols.opcua.endpoint --request '{"url": "..."}'
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("protocols.opcua.endpoint")
result = await operation.run(url=...)
```

## How it works

OPC UA.

OPC UA is a large protocol -- binary encoding, sessions, subscriptions,
an address space -- and a full client needs one.  ``asyncua`` is the
optional extra that provides it, and it is imported lazily.

What is implemented *here* is the part that is worth having without the
client: the endpoint.  An OPC UA endpoint URL carries the security
configuration in itself -- the scheme names the transport and the security
policy, the port names the profile -- and an operator who is auditing a
device wants exactly that, whether or not a session can be established.

## See also

* [the `protocols` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
