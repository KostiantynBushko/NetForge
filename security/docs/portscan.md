# `security.portscan`

> Scan the TCP ports of a host and report which of them are open.

**Risk:** Observability (level 2)  
**Category:** security  
**Tags:** `ports`, `scan`, `security`, `tcp`  
**Implementation:** `netforge.security.scanner:PortScannerOperation`

---

## What it does

Probes the TCP ports of a host and reports each one as open, closed or filtered. The scan opens and closes a connection per port, which the target can observe, so the operation is declared at the observability level rather than at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `host` | string | — | **Required.** The host to scan. (at least 1 character) |
| `ports` | list of integer or string | — | The ports to scan. A list of numbers, or a string of numbers and ranges. |
| `timeout` | number | `2.0` | Connect timeout per port. |
| `concurrency` | integer | `64` | How many ports to probe at once. (at least 1, at most 1024) |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | How long the scan took, in milliseconds. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `host` | string | The host that was scanned. |
| `results` | list of object | The result of every port that was scanned. |
| `open_ports` | list of integer | The ports that were open. |
| `closed_ports` | list of integer | The ports that were closed. |
| `filtered_ports` | list of integer | The ports that were filtered. |
| `scanned` | integer | How many ports were scanned. |

## Using it

### From the command line

```console
$ netforge run security.portscan --host <string>
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("security.portscan")
result = await operation.run(host=...)
```

## How it works

TCP port scanning.

The scanner opens a TCP connection to each port and records whether it was
accepted and how long the accept took.  A closed port is refused
immediately and a filtered port is dropped, and the difference between the
two is exactly what the scan tells you.

The scan is concurrent, with a bounded number of connections, and the port
list can be given as ranges.  The service names come from the system's own
services database.

## See also

* [the `security` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
