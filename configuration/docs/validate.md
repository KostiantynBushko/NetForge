# `configuration.validate`

> Check a configuration text for the problems that break a device.

**Risk:** Safe (level 1)  
**Category:** configuration  
**Tags:** `configuration`, `lint`, `validate`  
**Implementation:** `netforge.configuration.manager:ConfigurationValidateOperation`

---

## What it does

Checks a configuration text for trailing whitespace, tabs, a missing final newline, duplicated keys and unbalanced quotes. It changes nothing, so the operation is declared at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `content` | string | — | **Required.** The configuration text to validate. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `issues` | list of object | The problems that were found. |
| `error_count` | integer | How many of the problems are errors. |
| `warning_count` | integer | How many of the problems are warnings. |
| `valid` | boolean | Whether the configuration is valid. |

## Using it

### From the command line

```console
$ netforge run configuration.validate --content "..."
```

The values above are placeholders.  The request may also be given as a JSON object, which the flags are laid over:

```console
$ netforge run configuration.validate --request '{"content": "..."}'
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("configuration.validate")
result = await operation.run(content=...)
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
