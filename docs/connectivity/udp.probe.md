# `connectivity.udp.probe`

> Send a UDP datagram to a host and report whether it answered.

**Risk:** Observability (level 2)  
**Category:** connectivity  
**Tags:** `probe`, `reachability`, `udp`  
**Implementation:** `netforge.connectivity.udp:UdpProbeOperation`

---

## What it does

Sends a datagram to the given UDP port and waits for a reply. The probe is read-only in intent -- nothing is changed on the remote host -- but it does put bytes on the wire, which is why it is declared at the observability level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `host` | string | — | **Required.** The remote host. |
| `port` | integer | — | **Required.** The remote UDP port. (at least 1, at most 65535) |
| `payload` | string | `"netforge"` | The payload to send. |
| `timeout` | number | `5.0` | How long to wait for a reply. |
| `local_port` | integer | `0` | Local port to bind, 0 for any. (at least 0, at most 65535) |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `host` | string | The host that was probed. |
| `port` | integer | The port that was probed. |
| `replied` | boolean | Whether the host answered. |
| `latency_ms` | number | How long the answer took, in milliseconds. |
| `reply` | string | The datagram that came back. |
| `reply_bytes` | integer | How many bytes the answer holds. |
| `error` | string | Why the probe failed, when it did. |

## Using it

### From the command line

```console
$ netforge run connectivity.udp.probe --host <string> --port <integer>
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("connectivity.udp.probe")
result = await operation.run(host=..., port=...)
```

## How it works

UDP connectivity.

UDP has no session: there is no connect step that establishes state, only
a send that may or may not be answered.  The connection object here
therefore models the *endpoint* -- a local socket bound to a port, and the
remote address it talks to -- and the operation is the probe: send a
payload, wait for the answer, report what came back.

That distinction matters for the risk model: a UDP probe is read-only
observation, but it does send bytes to a third party, so it is declared at
level 2 (observability) rather than level 1.

## See also

* [the `connectivity` package](README.md) — every operation it publishes
* [the architecture](../ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../README.md)
