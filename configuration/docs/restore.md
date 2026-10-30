# `configuration.restore`

> Write a configuration file onto a device over SSH.

**Risk:** System Modification (level 4)  
**Category:** configuration  
**Tags:** `configuration`, `deploy`, `restore`, `ssh`  
**Implementation:** `netforge.configuration.manager:ConfigurationRestoreOperation`

---

## What it does

Writes a configuration file onto a device over SSH, copying the current file aside first. This changes the state of the device, which is why the operation is declared at the system modification level -- the highest one.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `host` | string | — | **Required.** The device to write to. (at least 1 character) |
| `path` | string | — | **Required.** The configuration file to write. (at least 1 character) |
| `content` | string | — | **Required.** The configuration to write. |
| `port` | integer | `22` | The SSH port. (at least 1, at most 65535) |
| `username` | string | — | The user to log in as. |
| `password` | string | — | The password, if one is needed. |
| `backup_first` | boolean | `true` | Copy the current file aside before writing. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `host` | string | The device the configuration was written to. |
| `path` | string | The path of the configuration that was written. |
| `written` | boolean | Whether the configuration was written. |
| `backup_path` | string | The path of the backup that was taken first. |
| `exit_code` | integer | The exit code of the command that wrote it. |

## Using it

### From the command line

```console
$ netforge run configuration.restore --host "..." --path "..." --content "..."
```

The values above are placeholders.  The request may also be given as a JSON object, which the flags are laid over:

```console
$ netforge run configuration.restore --request '{"host": "...", "path": "...", "content": "..."}'
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("configuration.restore")
result = await operation.run(host=..., path=..., content=...)
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
