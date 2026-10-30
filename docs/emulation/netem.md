# `emulation.netem`

> Apply, reset or show the network conditions of an interface.

**Risk:** System Modification (level 4)  
**Category:** emulation  
**Tags:** `emulation`, `latency`, `netem`, `network`, `tc`  
**Implementation:** `netforge.emulation.netem:NetEmOperation`

---

## What it does

Applies a network profile to an interface with the Linux traffic control tool, resets it, or reports what is currently applied. This changes the network of the machine it runs on, which is why the operation is declared at the system modification level.

> **This operation needs elevated privileges.**  It is refused when the process does not have them.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `interface` | string | — | **Required.** The interface to configure. (at least 1 character) |
| `profile` | string | — | The name of a preset profile. |
| `latency_ms` | number | — | A custom latency. |
| `jitter_ms` | number | — | A custom jitter. |
| `loss_percent` | number | — | A custom loss. |
| `bandwidth_mbps` | number | — | A custom bandwidth. |
| `action` | string | `"apply"` | 'apply', 'reset' or 'show'. |
| `dry_run` | boolean | `false` | Report the command without running it. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `interface` | string | The interface the conditions were applied to. |
| `action` | string | What was done: applied, reset or shown. |
| `command` | list of string | The command that was run. |
| `applied` | boolean | Whether the conditions were applied. |
| `qdisc` | list of object | The queueing discipline that is in place. |
| `profile` | object | The profile that was applied. |

## Using it

### From the command line

```console
$ netforge run emulation.netem --interface <string>
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("emulation.netem")
result = await operation.run(interface=...)
```

## How it works

Applying network conditions with ``tc``.

``tc`` -- the traffic control tool of Linux -- is what actually applies a
profile to an interface.  The class here builds the command line, runs it
through the framework's command runner, and parses what ``tc qdisc show``
reports.

Because it changes the network of the machine it runs on, the operation is
declared at the **system modification** level -- the highest one.

The class does not require ``tc`` to be installed to be *constructed* or
*tested*: the command line is built by a pure function, and the runner is
injected.  That is what makes it testable.

## See also

* [the `emulation` package](README.md) — every operation it publishes
* [the architecture](../ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../README.md)
