# `sentinel.log.analyse`

> Read the logs of a host and report the scans in them.

**Risk:** Safe (level 1)  
**Category:** security  
**Tags:** `auth`, `detection`, `firewall`, `forensics`, `logs`  
**Implementation:** `netforge.sentinel.logs:LogAnalysisOperation`

---

## What it does

Reads the authentication, firewall and web server logs of a host and reports what they say about scans: a burst of failed logins, a sweep refused by the firewall, and a run of requests that were refused. The logs are only read, so the operation is declared at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `path` | string | — | **Required.** The log file to read, or a directory of them. |
| `format` | string | `"auto"` | The format of the log: auto, syslog, ufw or access. |
| `window_seconds` | number | `300.0` | The window the rules look at. (more than 0.0) |
| `failures` | integer | `10` | How many failed logins make a burst. (at least 1) |
| `blocked_ports` | integer | `10` | How many refused ports make a sweep. (at least 1) |
| `errors` | integer | `20` | How many refused requests make a scan. (at least 1) |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | How long the analysis took. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `path` | string | The log that was read. |
| `alerts` | list of object | What was found. |
| `events` | integer | How many events were read. |
| `files` | integer | How many files were read. |

## Using it

### From the command line

```console
$ netforge run sentinel.log.analyse --path "..."
```

The values above are placeholders.  The request may also be given as a JSON object, which the flags are laid over:

```console
$ netforge run sentinel.log.analyse --request '{"path": "..."}'
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("sentinel.log.analyse")
result = await operation.run(path=...)
```

## How it works

The log half: reading what the machines already wrote down.

A packet capture is not the only record of a scan.  The host that was
scanned usually wrote the scan down as well -- in the authentication
log, in the firewall's log, in the web server's access log.  Those
records are already there, they need no privilege to read, and they
survive the monitor being stopped.

The parsers are the interesting part.  Each format has its own parser,
and each parser is a pure function over a text.  What they produce is
the same thing: a :class:`LogEvent`.  The rules are written against the
event, never against the format, so a rule that knows about a burst of
failed logins does not care whether it read them from sshd or from
journald -- and a new format is a new parser, with no rule to change.

## See also

* [the `security` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
