# `netforge.manipulation`

Controlled modification of traffic: a proxy that sits in the path and
forwards what it receives.

---

## Operations

| Operation | Risk | What it does |
|---|---|---|
| `manipulation.tcp.proxy` | Manipulation | Run a TCP proxy that forwards traffic to an upstream host and port. |

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

```text
class ProxyOperation
class ProxyRequest                      (*, listen_host='127.0.0.1', listen_port=0,
                                        upstream_host, upstream_port, duration=10.0)
class ProxyResponse                     (*, operation='', risk_level='', duration_ms=0.0,
                                        warnings=[], listen_host, listen_port, upstream,
                                        statistics={})
class ProxyStats                        (connections=0, bytes_client_to_upstream=0,
                                        bytes_upstream_to_client=0, errors=[])
class TcpProxy                          (listen_host, listen_port, upstream_host,
                                        upstream_port, *, timeout=30.0)

run_tcp_proxy(listen_host, listen_port, upstream_host, upstream_port, *,
              duration=None, timeout=30.0) -> ProxyStats
```

---

## Notes

* The proxy binds to `127.0.0.1` by default. Binding it to a routable
  address turns the machine into a relay, which is usually not what
  anyone wants.
* It forwards bytes; it does not parse them. Anything that understands the
  traffic — TLS, for instance — stays end to end.
* See also: [the architecture](ARCHITECTURE.md), [emulation.md](emulation.md).
