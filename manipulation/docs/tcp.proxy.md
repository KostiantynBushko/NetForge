# `manipulation.tcp.proxy`

> Run a TCP proxy that forwards traffic to an upstream host and port.

**Risk:** Manipulation (level 3)  
**Category:** manipulation  
**Tags:** `forward`, `intercept`, `proxy`, `tcp`  
**Implementation:** `netforge.manipulation.proxy:ProxyOperation`

---

## What it does

Runs a TCP proxy that accepts connections on one address and forwards them to another. The proxy sits in the path of the traffic, so the operation is declared at the manipulation level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `listen_host` | string | `"127.0.0.1"` | The address to listen on. |
| `listen_port` | integer | `0` | The port to listen on. 0 for any. (at least 0, at most 65535) |
| `upstream_host` | string | — | **Required.** The host to forward to. (at least 1 character) |
| `upstream_port` | integer | — | **Required.** The port to forward to. (at least 1, at most 65535) |
| `duration` | number | `10.0` | How long to run the proxy. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `listen_host` | string | The address the proxy listens on. |
| `listen_port` | integer | The port the proxy listens on. |
| `upstream` | string | The host and port the traffic is forwarded to. |
| `statistics` | object | What the proxy has forwarded so far. |

## Using it

### From the command line

```console
$ netforge run manipulation.tcp.proxy --upstream-host <string> --upstream-port <integer>
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("manipulation.tcp.proxy")
result = await operation.run(upstream_host=..., upstream_port=...)
```

## How it works

Traffic manipulation.

The proxies here are *controlled* manipulation: they forward traffic
faithfully, and the control is in what the operator configures -- the
listen address, the upstream address, whether the connection is allowed.

A plain TCP proxy is transparent to the protocol it carries.  An HTTP
proxy understands the request line and the ``CONNECT`` method, so it can
carry HTTPS through the tunnel without reading it.

Both are declared at the **manipulation** level: they are in the path of
the traffic, and the traffic they carry can be observed and changed.

## See also

* [the `manipulation` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
