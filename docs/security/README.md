# `netforge.security`

The focus here is assessment and diagnostics, not exploitation.

| Capability | What it does |
|---|---|
| **scanner** | which TCP ports are open, and how quickly they answer |
| **banner** | what is answering, and what does it say about itself |
| **tls** | what a TLS endpoint negotiates, and what its certificate says |
| **headers** | what an HTTP response's security headers say |

The first two are observable, so they sit at level 2. The last two are
read-only inspections of a service's own answers, so they sit at level 1.

A port scanner is not declared at the safe level even though it only opens
and closes a connection: a full sweep of a subnet is *visible* to the
target, and the risk model is about what the other side notices.

---

## Operations

<!-- generated:operations -->
| Operation | Risk | What it does |
|---|---|---|
| [`security.banner`](banner.md) | Observability | Read the banner a service sends when a client connects. |
| [`security.headers.analyze`](headers.analyze.md) | Safe | Analyse the security headers of an HTTP response. |
| [`security.portscan`](portscan.md) | Observability | Scan the TCP ports of a host and report which of them are open. |
| [`security.tls.inspect`](tls.inspect.md) | Safe | Inspect the TLS version, the cipher and the certificate of an endpoint. |
<!-- /generated:operations -->

---

## The port scanner

`PortScannerOperation` scans the TCP ports of a host.

`PortScanRequest(*, host, ports=[], timeout=2.0, concurrency=64)`:

| Field | Meaning |
|---|---|
| `host` | the target; at least one character |
| `ports` | a list of ports, or a string such as `"1-1024,443,8080"` |
| `timeout` | per-port timeout, greater than 0 |
| `concurrency` | how many ports to try at once, 1–1024 |

`PortScanResponse` reports `host`, the per-port `results`, and the
`open_ports`, `closed_ports` and `filtered_ports` lists, plus how many
ports were `scanned`.

---

## Banners

`grab_banner(host, port, *, probe=None, timeout=3.0, read_size=1024)`
returns a tuple of the banner text and the raw bytes, either of which may
be `None`.

```python
from netforge.security import grab_banner

text, raw = grab_banner("10.0.0.1", 22)
```

---

## TLS

`inspect_tls(host, port=443, *, timeout=5.0, verify=False,
server_hostname=None)` connects to a TLS endpoint and returns a
`TlsReport`: the `version` that was negotiated, the `cipher`, the
`peer_certificate`, the `subject_alternative_names`, whether the
certificate `verified`, and the `error` if the handshake failed.

`verify` defaults to `False` here, because the point of the inspection is
to look at an endpoint whose certificate is exactly what you want to
examine.

---

## Security headers

`analyze_headers(headers)` analyses a response's headers and reports what
is missing, as a list of findings. A `HeaderFinding` carries a `severity`,
the `header` it is about, a `message` and whether the header was
`present`.

`SECURITY_HEADERS` is the table of the headers it looks for, and their
severity.

```python
from netforge.security import analyze_headers

for finding in analyze_headers({"Server": "nginx"}):
    print(finding.severity, finding.message)
```

---

## Using it

```python
operation = registry.create("security.portscan")
result = await operation.run(host="10.0.0.1", ports="22,80,443")
print(result.open_ports)
```

---

## The public API

<!-- generated:public-api -->
```text
class BannerGrabOperation()
class HttpHeaderAnalysisOperation()
class PortScanRequest(*, host: str, ports: list[int] | str = [22, 80, 443], timeout: float | None = 2.0, concurrency: int = 64)
class PortScanResponse(*, operation: str = '', risk_level: str = '', duration_ms: float = 0.0, warnings: list[str] = [], host: str, results: list[dict[str, object]] = [], open_ports: list[int] = [], closed_ports: list[int] = [], filtered_ports: list[int] = [], scanned: int = 0)
class PortScannerOperation()
SECURITY_HEADERS = {'strict-transport-security': 'The connection is not pinn...
class TlsInspectionOperation()
def analyze_headers(headers: dict[str, str]) -> list[HeaderFinding]
def grab_banner(host: str, port: int, *, probe: bytes | None = None, timeout: float = 3.0, read_size: int = 1024) -> tuple[str | None, bytes | None]
def inspect_tls(host: str, port: int = 443, *, timeout: float = 5.0, verify: bool = False, server_hostname: str | None = None) -> TlsReport
```
<!-- /generated:public-api -->

---

## Two types that live in the submodules

`HeaderFinding` and `TlsReport` are part of the public surface of this
package — they are what the two functions above return — but they are not
re-exported from `netforge.security`, so import them from their own
modules:

```python
from netforge.security.headers import HeaderFinding
from netforge.security.tls import TlsReport
```

---

## Notes

* Nothing here exploits anything. Every capability reads what a service
  volunteers about itself.
* The scanner's `concurrency` is bounded at 1024, and its timeout is
  bounded above zero, because a scanner that fires without limit is a
  denial-of-service tool.
* `security.headers.analyze` works on a header dictionary, so it can be
  pointed at a response captured earlier without re-fetching it.
* See also: [the architecture](../ARCHITECTURE.md),
  [discovery.md](../discovery/README.md), [connectivity.md](../connectivity/README.md).
