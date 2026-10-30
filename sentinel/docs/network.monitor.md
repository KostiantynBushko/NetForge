# `sentinel.network.monitor`

> Watch an interface and report the scans that go past.

**Risk:** Observability (level 2)  
**Category:** security  
**Tags:** `detection`, `ids`, `live`, `monitor`, `scan`  
**Implementation:** `netforge.sentinel.network:NetworkMonitorOperation`

---

## What it does

Watches an interface with tcpdump and reports the scans it sees while it runs. The capture it made is written to a file, so that the same traffic can be read again with sentinel.network.analyse. Opening a raw socket needs a privilege, so the operation is declared at the observability level.

> **This operation needs elevated privileges.**  It is refused when the process does not have them.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `interface` | string | `"any"` | The interface to watch. |
| `duration` | number | `60.0` | How long to watch for. (at most 86400.0, more than 0.0) |
| `expression` | string | — | A BPF filter to narrow what is watched. |
| `output` | string | — | The capture file to write, so that it can be read again. |
| `sink` | string | — | The file the alerts are appended to, as JSON Lines. |
| `snaplen` | integer | `65535` | How many bytes of each packet to keep. (at least 64, at most 262144) |
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
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | What went wrong, if anything. |
| `interface` | string | The interface that was watched. |
| `alerts` | list of object | What was found. |
| `packets` | integer | How many packets were seen. |
| `attempts` | integer | How many connection attempts were seen. |
| `output` | string | The capture file that was written. |
| `sink` | string | The file the alerts were written to. |
| `duration_seconds` | number | How long the monitor ran. |

## Using it

### From the command line

```console
$ netforge run sentinel.network.monitor
```

The values above are placeholders.  The request may also be given as a JSON object, which the flags are laid over:

```console
$ netforge run sentinel.network.monitor --request '{}'
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("sentinel.network.monitor")
result = await operation.run()
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
