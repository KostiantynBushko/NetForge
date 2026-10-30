# `emulation.profile`

> Describe a network profile or list the built-in presets.

**Risk:** Safe (level 1)  
**Category:** emulation  
**Tags:** `conditions`, `emulation`, `network`, `profile`  
**Implementation:** `netforge.emulation.profile:ProfileOperation`

---

## What it does

Returns the network conditions of a preset -- bad WiFi, cellular, satellite, a constrained IoT link -- or describes a custom one. Nothing is applied to the network by this operation, so it is declared at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `name` | string | — | The name of a preset profile. |
| `latency_ms` | number | — | The latency to simulate. |
| `jitter_ms` | number | — | The jitter to simulate. |
| `loss_percent` | number | — | The packet loss. |
| `bandwidth_mbps` | number | — | The bandwidth limit. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `profile` | object | The profile that was described. |
| `presets` | list of string | The built-in presets. |
| `problems` | list of string | The problems the profile carries. |

## Using it

### From the command line

```console
$ netforge run emulation.profile
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("emulation.profile")
result = await operation.run()
```

## How it works

Network condition profiles.

A profile describes the network a device *thinks* it is on: the latency,
the jitter, the loss, the bandwidth.  The profiles are pure data, and the
presets -- bad WiFi, cellular, satellite, a constrained IoT link -- are the
four cases the specification names.

The analysis of a profile is also pure: :func:`grade_profile` says whether
a profile is internally consistent and how severe it is, which is what an
agent needs before it applies one.

## See also

* [the `emulation` package](README.md) — every operation it publishes
* [the architecture](../ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../README.md)
