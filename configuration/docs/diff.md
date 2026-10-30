# `configuration.diff`

> Compare two configuration texts and report the difference.

**Risk:** Safe (level 1)  
**Category:** configuration  
**Tags:** `compare`, `configuration`, `diff`  
**Implementation:** `netforge.configuration.manager:ConfigurationDiffOperation`

---

## What it does

Produces a unified diff between the current configuration and a candidate one. It is a pure comparison, so the operation is declared at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `current` | string | — | **Required.** The configuration as it is now. |
| `candidate` | string | — | **Required.** The configuration as it should be. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `diff` | list of string | The difference between the two configurations. |
| `identical` | boolean | Whether the two configurations are the same. |
| `changed_lines` | integer | How many lines differ. |

## Using it

### From the command line

```console
$ netforge run configuration.diff --request '{"current": "...", "candidate": "..."}'
```

The request is a JSON object, and the values above are placeholders.

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("configuration.diff")
result = await operation.run(current=..., candidate=...)
```

## How it works

Configuration management.

The configuration capability has four operations, and the split between
them is the point:

``configuration.validate``
    Check a configuration text for the problems that break a device.
    Pure, offline, safe.

``configuration.diff``
    Compare two configuration texts.  Pure, offline, safe.

``configuration.backup``
    Read a configuration off a device.  Read-only, safe.

``configuration.restore``
    Write a configuration onto a device.  Modifies the device, so it is
    declared at the **system modification** level.

The first two are pure functions on purpose: they are the operations an
operator runs *before* touching a device, and they must work on a laptop
with no network and no credentials.

## See also

* [the `configuration` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
