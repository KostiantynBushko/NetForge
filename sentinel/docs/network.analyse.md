# `sentinel.network.analyse`

> Read a capture file and report the scans that are in it.

**Risk:** Safe (level 1)  
**Category:** security  
**Tags:** `detection`, `forensics`, `pcap`, `scan`  
**Implementation:** `netforge.sentinel.network:NetworkAnalysisOperation`

---

## What it does

Reads a libpcap file, rebuilds the connection attempts it holds and reports the scans among them: a sweep over many ports, a half-open scan, a burst of empty connections, and a service probe. The file is only read, so the operation is declared at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `path` | string | — | **Required.** The capture file to read. |
| `window_seconds` | number | `60.0` | The window the rules look at. (more than 0.0) |
| `distinct_ports` | integer | `10` | How many different ports make a sweep. (at least 1) |
| `half_open` | integer | `5` | How many closed ports make a half-open scan. (at least 1) |
| `silent_handshakes` | integer | `10` | How many empty connections make a scan. (at least 1) |
| `service_probes` | integer | `3` | How many probed ports make a service probe. (at least 1) |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | How long the analysis took. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `path` | string | The capture file that was read. |
| `alerts` | list of object | What was found. |
| `packets` | integer | How many packets were read. |
| `attempts` | integer | How many connection attempts were seen. |
| `sources` | integer | How many addresses took part. |

## Using it

### From the command line

```console
$ netforge run sentinel.network.analyse --path "..."
```

The values above are placeholders.  The request may also be given as a JSON object, which the flags are laid over:

```console
$ netforge run sentinel.network.analyse --request '{"path": "..."}'
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("sentinel.network.analyse")
result = await operation.run(path=...)
```

## How it works

The network operations: watching the traffic, and reading it back.

Two operations, one engine:

``sentinel.network.analyse``
    reads a capture file and reports what is in it.  It needs nothing
    but the file, so it runs anywhere, it needs no privilege, and it
    gives the same answer every time.

``sentinel.network.monitor``
    watches an interface while it runs.  It needs the privilege to open
    a raw socket, and it writes the capture it made -- so that the
    offline analyser can be run over it afterwards, and so that nothing
    is lost when the monitor is stopped.

The monitor is a convenience; the analyser is the truth.  A capture is a
record, and a record can be read again.

## See also

* [the `security` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
