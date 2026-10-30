# `capture.session`

> Capture packets from an interface into a libpcap file.

**Risk:** Observability (level 2)  
**Category:** capture  
**Tags:** `capture`, `pcap`, `tcpdump`, `traffic`  
**Implementation:** `netforge.capture.session:CaptureOperation`

---

## What it does

Runs a packet capture on an interface for a fixed duration and writes the result to a libpcap file. The capture observes traffic without changing it, which is why the operation is declared at the observability level. It needs the privilege to open a raw socket.

> **This operation needs elevated privileges.**  It is refused when the process does not have them.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `interface` | string | `"any"` | The interface to capture on. |
| `output` | string | — | **Required.** The path of the capture file to write. |
| `duration` | number | `10.0` | How long to capture for. (at most 3600.0, more than 0.0) |
| `protocol` | string | — | Filter by protocol, e.g. 'tcp'. |
| `host` | string | — | Filter by host. |
| `port` | integer | — | Filter by port. |
| `source` | string | — | Filter by source address. |
| `destination` | string | — | Filter by destination address. |
| `direction` | string | — | Filter by direction: inbound or outbound. |
| `expression` | string | — | A raw BPF expression to use as-is. |
| `snaplen` | integer | `65535` | How many bytes of each packet to keep. (at least 64, at most 262144) |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `output` | string | The path of the capture file that was written. |
| `interface` | string | The interface the packets were captured from. |
| `expression` | string | The filter the capture was filtered by. |
| `duration_seconds` | number | How long the capture ran, in seconds. |
| `bytes_written` | integer | How many bytes were written to the capture file. |
| `packets` | integer | How many packets were captured. |

## Using it

### From the command line

```console
$ netforge run capture.session --output <string>
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("capture.session")
result = await operation.run(output=...)
```

## How it works

Traffic capture.

A capture session runs ``tcpdump`` (or ``dumpcap``) and writes a libpcap
file.  The filter is a BPF expression, and the filter *builder* -- which
produces one -- is implemented here as a pure function over a small model,
so a filter can be built, inspected and tested without a capture running.

The session itself is the one part that needs the system tool.  It is
started as a subprocess, and it is stopped by sending ``SIGINT``, which is
how ``tcpdump`` is asked to flush its buffer and close the file cleanly.

## See also

* [the `capture` package](README.md) — every operation it publishes
* [the architecture](../ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../README.md)
