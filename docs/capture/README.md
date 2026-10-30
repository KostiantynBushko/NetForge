# `netforge.capture`

A capture session runs the system capture tool and writes a libpcap file.

The BPF filter builder is a pure function over a small model, so a filter
can be constructed and checked without a capture running.

---

## Operations

<!-- generated:operations -->
| Operation | Risk | What it does |
|---|---|---|
| [`capture.session`](session.md) | Observability | Capture packets from an interface into a libpcap file. |
<!-- /generated:operations -->

A capture is declared *observability* rather than *safe*: it does not touch
the network, but it does read the traffic on it, and it is plainly visible
to everyone else on the wire.

---

## The BPF filter

`BpfFilter` builds a BPF expression from a small model, and it is a pure
function — no capture, no privileges, no side effects.

```python
from netforge.capture import BpfFilter

BpfFilter(host="10.0.0.1", port=443).to_expression()
# 'host 10.0.0.1 and port 443'
```

| Field | Produces |
|---|---|
| `host` | `host <value>` |
| `port` | `port <value>` |
| `protocol` | `<value>` |
| `source` | `src <value>` |
| `destination` | `dst <value>` |
| `direction` | the direction qualifier |
| `extra` | appended verbatim |
| `parts` | the assembled parts, in order |

---

## The session

`CaptureSession(interface, output, *, filter_expression=None, snaplen=65535, command='tcpdump', timeout=30.0)`
is a running capture session. It starts the system capture tool, waits for
the duration, and stops it cleanly so the file is flushed and closed
properly.

The `command` is configurable, so `dumpcap` works as well as `tcpdump`.

---

## The request and response

`CaptureFilterRequest` is the request of the operation:

| Field | Default | Constraint |
|---|---|---|
| `interface` | `"any"` | |
| `output` | — | required |
| `duration` | `10.0` | greater than 0, at most 3600 seconds |
| `protocol`, `host`, `source`, `destination`, `direction`, `expression` | `None` | |
| `port` | `None` | 1–65535 |
| `snaplen` | `65535` | 64–262144 |

`CaptureResponse` reports `output`, `interface`, `expression`,
`duration_seconds`, `bytes_written` and `packets`.

---

## Using it

```python
operation = registry.create("capture.session")
result = await operation.run(
    interface="any",
    output="/tmp/capture.pcap",
    duration=10,
    host="10.0.0.1",
    port=443,
)
```

And to read it back, see [analysis.md](../analysis/README.md).

---

## The public API

<!-- generated:public-api -->
```text
class BpfFilter(host: str | None = None, port: int | None = None, protocol: str | None = None, source: str | None = None, destination: str | None = None, direction: str | None = None, extra: str | None = None, parts: list[str] = <factory>)
class CaptureFilterRequest(*, interface: str = 'any', output: str, duration: float = 10.0, protocol: str | None = None, host: str | None = None, port: int | None = None, source: str | None = None, destination: str | None = None, direction: str | None = None, expression: str | None = None, snaplen: int = 65535)
class CaptureOperation()
class CaptureResponse(*, operation: str = '', risk_level: str = '', duration_ms: float = 0.0, warnings: list[str] = [], output: str, interface: str, expression: str = '', duration_seconds: float = 0.0, bytes_written: int = 0, packets: int | None = None)
class CaptureSession(interface: str, output: Path, *, filter_expression: str | None = None, snaplen: int = 65535, command: str = 'tcpdump', timeout: float | None = 30.0)
```
<!-- /generated:public-api -->

---

## Notes

* The capture runs the *system* tool. It needs `tcpdump` (or `dumpcap`)
  installed and enough privileges to open the interface — usually root.
* `capture_directory` in the configuration is the default place captures
  are written; `NETFORGE_CAPTURE_DIRECTORY` overrides it.
* Nothing here imports `scapy`. The capture is a subprocess and the
  analysis reads the file with the standard library — see
  [analysis.md](../analysis/README.md).
* See also: [the architecture](../ARCHITECTURE.md), [analysis.md](../analysis/README.md).
