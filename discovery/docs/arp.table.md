# `discovery.arp.table`

> Read the local ARP neighbour table.

**Risk:** Safe (level 1)  
**Category:** discovery  
**Tags:** `arp`, `local`, `mac`, `neighbour`  
**Implementation:** `netforge.discovery.arp:ArpTableOperation`

---

## What it does

Reads the kernel's ARP neighbour table and returns the IP address, the hardware address, the flags and the interface of every entry. Reading the table changes nothing, so the operation is declared at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `path` | string | `"/proc/net/arp"` | The file to read. Defaults to the kernel's neighbour table. |
| `complete_only` | boolean | `false` | Only return entries with a resolved MAC. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `entries` | list of object | The neighbours in the table. |
| `source` | string | Where the table was read from. |
| `total` | integer | How many neighbours there are. |

## Using it

### From the command line

```console
$ netforge run discovery.arp.table
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("discovery.arp.table")
result = await operation.run()
```

## How it works

The ARP table.

On Linux the neighbour table lives in ``/proc/net/arp``.  It is a small,
stable, comma-separated text format, and reading it needs no privilege at
all -- which makes it the cheapest useful piece of local network
information there is.

The parser is a pure function over text, so it can be checked against a
captured sample without a Linux kernel.

## See also

* [the `discovery` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
