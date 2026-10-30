# `discovery.route.table`

> Read the local routing table.

**Risk:** Safe (level 1)  
**Category:** discovery  
**Tags:** `gateway`, `local`, `route`, `routing`  
**Implementation:** `netforge.discovery.route:RouteTableOperation`

---

## What it does

Reads the kernel's routing table and returns the destination, the gateway, the netmask, the interface and the metric of every route.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `path` | string | `"/proc/net/route"` | The file to read. Defaults to the kernel's IPv4 routing table. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `entries` | list of object | The routes of the table. |
| `source` | string | Where the table was read from. |
| `total` | integer | How many routes there are. |

## Using it

### From the command line

```console
$ netforge run discovery.route.table
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("discovery.route.table")
result = await operation.run()
```

## How it works

The routing table.

``/proc/net/route`` holds the IPv4 routing table and ``/proc/net/ipv6_route``
the IPv6 one.  Both are text, both are readable without privilege, and
both are parsed here by pure functions.

The hexadecimal encoding in ``/proc/net/route`` is worth stating plainly:
the destination and the gateway are 32-bit values in *host* byte order,
printed as eight hexadecimal digits.  ``0102A8C0`` is ``192.168.2.1``.

## See also

* [the `discovery` package](README.md) — every operation it publishes
* [the architecture](../ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../README.md)
