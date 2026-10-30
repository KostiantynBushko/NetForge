# `discovery.traceroute`

> Trace the network path to a host and report every hop.

**Risk:** Safe (level 1)  
**Category:** discovery  
**Tags:** `latency`, `path`, `route`, `traceroute`  
**Implementation:** `netforge.discovery.traceroute:TracerouteOperation`

---

## What it does

Runs traceroute towards a host and reports each hop, the address it answered from and the round-trip times. The trace is read-only observation of the path, so the operation is declared at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `host` | string | — | **Required.** The host to trace the route to. (at least 1 character) |
| `max_hops` | integer | `30` | The maximum number of hops. (at least 1, at most 64) |
| `timeout` | number | `5.0` | Per-probe timeout in seconds. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `host` | string | The host that was traced. |
| `hops` | list of object | The hops of the path. |
| `reached` | boolean | Whether the host was reached. |

## Using it

### From the command line

```console
$ netforge run discovery.traceroute --host "..."
```

The values above are placeholders.  The request may also be given as a JSON object, which the flags are laid over:

```console
$ netforge run discovery.traceroute --request '{"host": "..."}'
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("discovery.traceroute")
result = await operation.run(host=...)
```

## How it works

Traceroute.

Like ping, traceroute shells out to the system tool.  The output parser
handles the Linux and the BSD shapes, which differ in the separator between
the hops and in the way the address is annotated.

## See also

* [the `discovery` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
