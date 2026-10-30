# `discovery.ping`

> Send ICMP echo requests to a host and report the round-trip times.

**Risk:** Safe (level 1)  
**Category:** discovery  
**Tags:** `icmp`, `ping`, `reachability`  
**Implementation:** `netforge.discovery.ping:PingOperation`

---

## What it does

Pings a host with the system ping utility and reports whether it answered, the packet loss and the minimum, average and maximum round-trip times.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `host` | string | — | **Required.** The host or address to ping. (at least 1 character) |
| `count` | integer | `3` | How many echo requests to send. (at least 1, at most 100) |
| `timeout` | number | `5.0` | Per-packet timeout in seconds. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `host` | string | The host that was pinged. |
| `reachable` | boolean | Whether the host answered. |
| `loss_percent` | number | How many of the probes were lost, in percent. |
| `min_ms` | number | The shortest round trip, in milliseconds. |
| `avg_ms` | number | The mean round trip, in milliseconds. |
| `max_ms` | number | The longest round trip, in milliseconds. |

## Using it

### From the command line

```console
$ netforge run discovery.ping --host "..."
```

The values above are placeholders.  The request may also be given as a JSON object, which the flags are laid over:

```console
$ netforge run discovery.ping --request '{"host": "..."}'
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("discovery.ping")
result = await operation.run(host=...)
```

## How it works

ICMP echo -- ping.

``ping`` is a system tool on every platform NetForge runs on, so the
capability shells out to it rather than opening a raw socket.  A raw
socket would need ``CAP_NET_RAW`` or root, and the capability would then
only work for the privileged: an unprivileged ping works for everybody.

The parsing is separate from the invocation, so the output of a captured
``ping`` run can be checked without running ``ping``.

## See also

* [the `discovery` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
