# `discovery.service.enumerate`

> Probe the ports of a host and name the services that are listening.

**Risk:** Observability (level 2)  
**Category:** discovery  
**Tags:** `enumeration`, `ports`, `service`  
**Implementation:** `netforge.discovery.service:ServiceDiscoveryOperation`

---

## What it does

Probes a set of TCP ports on a host and reports which of them are open, together with the service name from the system's own services database. The probe opens and closes a connection per port, which is observable on the wire, so the operation is declared at the observability level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `host` | string | — | **Required.** The host to inspect. |
| `ports` | list of integer | — | The ports to probe. An empty list uses the common set. |
| `timeout` | number | `2.0` | Connect timeout per port. |
| `concurrency` | integer | `32` | How many probes to run at once. (at least 1, at most 256) |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `host` | string | The host that was probed. |
| `open_ports` | list of object | The ports that were open, and the services on them. |
| `closed_ports` | list of integer | The ports that were closed. |
| `scanned` | integer | How many ports were probed. |

## Using it

### From the command line

```console
$ netforge run discovery.service.enumerate --host <string>
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("discovery.service.enumerate")
result = await operation.run(host=...)
```

## How it works

Service discovery.

Service discovery is the combination of a port probe and an identification:
which ports are open, and what is listening on them.

The service names come from the system's own database (``/etc/services``
through :mod:`socket`), so the answer is the one the machine itself would
give, and not a table hard-coded in NetForge.

## See also

* [the `discovery` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
