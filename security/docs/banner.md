# `security.banner`

> Read the banner a service sends when a client connects.

**Risk:** Observability (level 2)  
**Category:** security  
**Tags:** `banner`, `fingerprint`, `grab`, `service`  
**Implementation:** `netforge.security.banner:BannerGrabOperation`

---

## What it does

Connects to a service and reads the banner it sends, optionally sending the protocol's usual probe first. The connection is visible to the service, which is why the operation is declared at the observability level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `host` | string | — | **Required.** The host to talk to. (at least 1 character) |
| `port` | integer | — | **Required.** The port to talk to. (at least 1, at most 65535) |
| `protocol` | string | — | The protocol name, used to pick the probe: http, ftp, smtp, ... |
| `timeout` | number | `3.0` | Read timeout in seconds. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `host` | string | The host the banner came from. |
| `port` | integer | The port the banner came from. |
| `banner` | string | The banner, as text. |
| `raw` | string | The banner, as it was received. |
| `bytes` | integer | How many bytes the banner holds. |

## Using it

### From the command line

```console
$ netforge run security.banner --host <string> --port <integer>
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("security.banner")
result = await operation.run(host=..., port=...)
```

## How it works

Banner grabbing.

A banner is the string a service sends before it is asked anything: the
SSH version, the SMTP greeting, the HTTP response line.  It identifies the
software and often its version, which is exactly what an assessment needs.

Some services send their banner unprompted and some wait to be spoken to.
The grabber knows both: it reads first, and if nothing arrives it sends the
protocol's usual probe -- ``\r\n`` for FTP, ``HEAD / HTTP/1.0\r\n\r\n``
for HTTP -- and reads again.

## See also

* [the `security` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
