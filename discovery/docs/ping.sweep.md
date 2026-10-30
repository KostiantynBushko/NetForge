# `discovery.ping.sweep`

> Ping every address of a network and report the hosts that answer.

**Risk:** Observability (level 2)  
**Category:** discovery  
**Tags:** `cidr`, `network`, `ping`, `sweep`  
**Implementation:** `netforge.discovery.sweep:PingSweepOperation`

---

## What it does

Expands a CIDR block, an address range or a single address and pings every host in it, concurrently. The addresses that answer are reported as the alive set. The sweep puts traffic on the network, which is why it is declared at the observability level rather than at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `network` | string | — | **Required.** The CIDR block, address range or single address to sweep. |
| `concurrency` | integer | `32` | How many pings to run at once. (at least 1, at most 512) |
| `count` | integer | `1` | How many echo requests per host. (at least 1, at most 10) |
| `timeout` | number | `3.0` | Per-packet timeout in seconds. |
| `max_hosts` | integer | `1024` | The largest network that may be swept. (at least 1) |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `network` | string | The network that was swept. |
| `scanned` | integer | How many addresses were swept. |
| `alive` | list of string | The addresses that answered. |
| `unreachable` | list of string | How many addresses did not answer. |
| `details` | list of object | The details of every address that was swept. |

## Using it

### From the command line

```console
$ netforge run discovery.ping.sweep --network <string>
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("discovery.ping.sweep")
result = await operation.run(network=...)
```

## How it works

Ping sweeps.

A sweep is a ping against every address of a network, run concurrently.
The address expansion is done with :mod:`ipaddress`, so a CIDR, a range
and a bare address all work, and the sweep refuses a network that is larger
than the caller asked for -- a /8 is 16 million hosts, and nobody means to
type that by accident.

## See also

* [the `discovery` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
