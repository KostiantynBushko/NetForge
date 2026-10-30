# `netforge.manipulation`

Controlled modification of traffic: a proxy that sits in the path and
forwards what it receives.

---

## Operations

<!-- generated:operations -->
| Operation | Risk | What it does |
|---|---|---|
| [`manipulation.tcp.proxy`](tcp.proxy.md) | Manipulation | Run a TCP proxy that forwards traffic to an upstream host and port. |
<!-- /generated:operations -->

The proxy does not alter what it forwards — it is transparent. What makes
it a *manipulation* is that traffic is redirected through it, and that is
visible on both sides of the connection.

---

## The proxy

`TcpProxy(listen_host, listen_port, upstream_host, upstream_port, *,
timeout=30.0)` is a transparent TCP proxy. It accepts connections on the
listening address and forwards each one to the upstream.

`run_tcp_proxy(listen_host, listen_port, upstream_host, upstream_port, *,
duration=None, timeout=30.0)` runs it for `duration` seconds and returns
its statistics.

```python
from netforge.manipulation import run_tcp_proxy

stats = run_tcp_proxy("127.0.0.1", 9090, "10.0.0.1", 80, duration=30.0)
print(stats.connections, stats.bytes_client_to_upstream)
```

---

## The statistics

`ProxyStats` is what the proxy has done so far:

| Field | Meaning |
|---|---|
| `connections` | how many connections it handled |
| `bytes_client_to_upstream` | bytes forwarded towards the upstream |
| `bytes_upstream_to_client` | bytes forwarded back |
| `errors` | anything that went wrong, in words |

---

## The request and response

`ProxyRequest(*, listen_host='127.0.0.1', listen_port=0,
upstream_host, upstream_port, duration=10.0)` — `listen_port=0` asks the
operating system for a free port, and the response reports which one was
chosen.

`ProxyResponse` reports `listen_host`, `listen_port`, `upstream` and the
`statistics`.

---

## Using it

```python
operation = registry.create("manipulation.tcp.proxy")
result = await operation.run(
    listen_host="127.0.0.1",
    upstream_host="10.0.0.1",
    upstream_port=80,
    duration=30.0,
)
print(result.statistics)
```

---

## The public API

<!-- generated:public-api -->
```text
class ProxyOperation()
class ProxyRequest(*, listen_host: str = '127.0.0.1', listen_port: int = 0, upstream_host: str, upstream_port: int, duration: float | None = 10.0)
class ProxyResponse(*, operation: str = '', risk_level: str = '', duration_ms: float = 0.0, warnings: list[str] = [], listen_host: str, listen_port: int, upstream: str, statistics: dict[str, object] = {})
class ProxyStats(connections: int = 0, bytes_client_to_upstream: int = 0, bytes_upstream_to_client: int = 0, errors: list[str] = <factory>)
class TcpProxy(listen_host: str, listen_port: int, upstream_host: str, upstream_port: int, *, timeout: float | None = 30.0)
def run_tcp_proxy(listen_host: str, listen_port: int, upstream_host: str, upstream_port: int, *, duration: float | None = None, timeout: float | None = 30.0) -> ProxyStats
```
<!-- /generated:public-api -->

---

## Notes

* The proxy binds to `127.0.0.1` by default. Binding it to a routable
  address turns the machine into a relay, which is usually not what
  anyone wants.
* It forwards bytes; it does not parse them. Anything that understands the
  traffic — TLS, for instance — stays end to end.
* See also: [the architecture](../ARCHITECTURE.md), [emulation.md](../emulation/README.md).
