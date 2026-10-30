# `sentinel.alert.list`

> Read the alerts out of the file the sentinel keeps them in.

**Risk:** Safe (level 1)  
**Category:** security  
**Tags:** `alerts`, `detection`, `report`  
**Implementation:** `netforge.sentinel.alerts:AlertListOperation`

---

## What it does

Reads the alerts the sentinel has written, and reports them newest last, with a count of how many there are of each severity and of each rule. The file is only read, so the operation is declared at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `path` | string | — | **Required.** The sink the alerts are kept in. |
| `since` | number | — | Only the alerts after this Unix timestamp. |
| `severity` | string | — | Only the alerts of this severity. |
| `rule` | string | — | Only the alerts of this rule. |
| `limit` | integer | `100` | How many alerts to report. (at least 1, at most 10000) |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `path` | string | The sink that was read. |
| `alerts` | list of object | The alerts. |
| `total` | integer | How many alerts the sink holds. |
| `by_severity` | object | How many alerts of each severity. |
| `by_rule` | object | How many alerts of each rule. |

## Using it

### From the command line

```console
$ netforge run sentinel.alert.list --path "..."
```

The values above are placeholders.  The request may also be given as a JSON object, which the flags are laid over:

```console
$ netforge run sentinel.alert.list --request '{"path": "..."}'
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("sentinel.alert.list")
result = await operation.run(path=...)
```

## How it works

The alerts, and the file they are kept in.

An alert is a named event with the evidence behind it.  The evidence is
what makes an alert worth reading: "ten ports in a second" is a number,
"ten ports in a second, and here they are" is a finding.

The alerts are kept in a JSON Lines file: one JSON object per line,
appended as they are found.  The format is plain enough to grep, and
plain enough for another program to read without a schema.

## See also

* [the `security` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
