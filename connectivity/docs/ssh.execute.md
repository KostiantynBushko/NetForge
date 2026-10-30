# `connectivity.ssh.execute`

> Run a shell command on a remote host over SSH.

**Risk:** Manipulation (level 3)  
**Category:** connectivity  
**Tags:** `command`, `remote`, `ssh`  
**Implementation:** `netforge.connectivity.ssh:SshExecuteOperation`

---

## What it does

Runs a shell command on a remote host over SSH and returns its exit code and output. The command may change the state of the remote system, which is why the operation is declared at the manipulation level rather than at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `host` | string | — | **Required.** The remote host. |
| `command` | string | — | **Required.** The command to run. (at least 1 character) |
| `port` | integer | `22` | The SSH port. (at least 1, at most 65535) |
| `username` | string | — | The user to log in as. |
| `password` | string | — | The password, if one is needed. |
| `client_keys` | list of string | — | Paths of the client keys. |
| `timeout` | number | `30.0` | Timeout in seconds. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | How long the command took, in milliseconds. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `host` | string | The host the command ran on. |
| `command` | string | The command that was run. |
| `exit_code` | integer | The exit code of the command. |
| `stdout` | string | What the command wrote to the standard output. |
| `stderr` | string | What the command wrote to the standard error. |

## Using it

### From the command line

```console
$ netforge run connectivity.ssh.execute --host "..." --command "..."
```

The values above are placeholders.  The request may also be given as a JSON object, which the flags are laid over:

```console
$ netforge run connectivity.ssh.execute --request '{"host": "...", "command": "..."}'
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("connectivity.ssh.execute")
result = await operation.run(host=..., command=...)
```

## How it works

SSH connectivity.

SSH is the transport for the whole configuration capability: backing up a
device, restoring a configuration, running a command.

``asyncssh`` is an optional extra.  It is imported lazily, inside
:func:`_load_asyncssh`, so the module can be imported -- and the operation
can be *listed* -- on a machine that does not have it.  Running the
operation without the extra raises
:class:`~netforge.core.exceptions.DependencyMissingError`, which names the
extra to install.

The risk level of a remote command is **manipulation** (level 3): the
command may change the state of the remote system, and NetForge does not
know which command it was asked to run.

## See also

* [the `connectivity` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
