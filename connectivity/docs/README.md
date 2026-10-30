# `netforge.connectivity`

Connectivity is how NetForge reaches remote systems: SSH, HTTP, WebSocket,
TCP and UDP.

Each of them is a *connection* — a reusable object with a lifecycle — and,
where it makes sense, an *operation* that exposes the capability to
adapters.

The connections are written against `asyncio` and the standard library.
`asyncssh` is the single exception and is an optional extra: the SSH
connection imports it lazily and reports a clear error when it is missing,
so the rest of the framework works on a machine without it.

---

## Operations

<!-- generated:operations -->
| Operation | Risk | What it does |
|---|---|---|
| [`connectivity.http.request`](http.request.md) | Safe | Perform an HTTP request and report the status, headers and body. |
| [`connectivity.ssh.execute`](ssh.execute.md) | Manipulation | Run a shell command on a remote host over SSH. |
| [`connectivity.tcp.connect`](tcp.connect.md) | Safe | Open a TCP connection to a host and port and report whether it succeeded. |
| [`connectivity.udp.probe`](udp.probe.md) | Observability | Send a UDP datagram to a host and report whether it answered. |
<!-- /generated:operations -->

A TCP connect is declared *safe* because it opens a connection and closes
it again, without sending anything the other side would notice. A UDP
probe is one level higher: sending a datagram is visible to the target.

---

## The connection lifecycle

`Connection` is the base class, and `ConnectionState` is the lifecycle
state it moves through.

<!-- generated:public-api -->
```text
class Connection(*, timeout: float | None = 30.0)
class ConnectionResult(ok: bool, stdout: str = '', stderr: str = '', exit_code: int | None = None, duration_ms: float = 0.0, metadata: dict[str, Any] = <factory>)
class ConnectionState()
class HttpConnection(*, timeout: float | None = 30.0, verify_tls: bool = True, user_agent: str = 'netforge/0.1.0', headers: dict[str, str] | None = None)
class HttpRequestOperation()
class TcpConnectOperation()
class TcpConnection(host: str, port: int, *, timeout: float | None = 30.0)
class UdpConnection(host: str, port: int, *, local_host: str = '0.0.0.0', local_port: int = 0, timeout: float | None = 30.0)
class UdpProbeOperation()
class WebSocketConnection(url: str, *, timeout: float | None = 30.0, extra_headers: dict[str, str] | None = None)
```
<!-- /generated:public-api -->

`ConnectionResult` is the outcome of a command or transfer over a
connection: `ok`, `stdout`, `stderr`, `exit_code`, `duration_ms` and
`metadata`.

---

## The connections

| Class | What it is |
|---|---|
| `TcpConnection(host, port, *, timeout=30.0)` | a TCP connection to a remote host and port |
| `UdpConnection(host, port, *, local_host='0.0.0.0', local_port=0, timeout=30.0)` | a UDP endpoint bound to a local socket |
| `HttpConnection(*, timeout=30.0, verify_tls=True, user_agent='netforge/0.1.0', headers=None)` | a small HTTP client on the standard library |
| `WebSocketConnection(url, *, timeout=30.0, extra_headers=None)` | a WebSocket client connection |

---

## Using it

```python
from netforge.connectivity import TcpConnection

async with TcpConnection("10.0.0.1", 22) as connection:
    print(connection.state)
```

And through the framework, which is how an adapter reaches it:

```python
operation = registry.create("connectivity.tcp.connect")
result = await operation.run(host="10.0.0.1", port=22)
```

---

## The public API

```text
class Connection                                        (*, timeout=30.0)
class ConnectionResult                                  (ok, stdout='', stderr='',
                                                         exit_code=None,
                                                         duration_ms=0.0, metadata={})
class ConnectionState(Enum)
class HttpConnection                                    (*, timeout=30.0, verify_tls=True,
                                                         user_agent='netforge/0.1.0',
                                                         headers=None)
class HttpRequestOperation
class TcpConnectOperation
class TcpConnection                                     (host, port, *, timeout=30.0)
class UdpConnection                                     (host, port, *, local_host='0.0.0.0',
                                                         local_port=0, timeout=30.0)
class UdpProbeOperation
class WebSocketConnection                               (url, *, timeout=30.0,
                                                         extra_headers=None)
```

---

## Notes

* The HTTP client here is deliberately small and standard-library only.
  The richer HTTP *protocol* adapter lives in
  [protocols.md](../../protocols/docs/README.md); this one is the transport the
  `connectivity.http.request` operation uses.
* `verify_tls` defaults to `True` and is also settable through
  `NETFORGE_VERIFY_TLS`.
* The SSH connection is not re-exported from the package's `__all__`,
  because importing it eagerly would need `asyncssh`. It is available as
  `netforge.connectivity.ssh` and is used by
  [configuration.md](../../configuration/docs/README.md).
* See also: [the architecture](../../docs/ARCHITECTURE.md), [protocols.md](../../protocols/docs/README.md),
  [discovery.md](../../discovery/docs/README.md).
