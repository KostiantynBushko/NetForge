# `protocols.http.request`

> Speak the HTTP protocol against an endpoint and report the reply.

**Risk:** Safe (level 1)  
**Category:** protocols  
**Tags:** `http`, `protocol`, `request`  
**Implementation:** `netforge.protocols.http:HttpProtocolOperation`

---

## What it does

Performs an HTTP request and returns the status, the headers and the body. This is the protocol-level view of the HTTP capability; the connectivity operation offers the same thing with a different taxonomy.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `url` | string | — | **Required.** The absolute URL to request. |
| `method` | string | `"GET"` | The HTTP method. |
| `headers` | object | — | Extra request headers. |
| `body` | string | — | The request body. |
| `timeout` | number | — | Timeout in seconds. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `url` | string | The URL that was requested. |
| `method` | string | The HTTP method that was used. |
| `status` | integer | The status code of the response. |
| `headers` | object | The headers of the response. |
| `body` | string | The body of the response. |
| `elapsed_ms` | number | How long the request took, in milliseconds. |

## Using it

### From the command line

```console
$ netforge run protocols.http.request --url <string>
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("protocols.http.request")
result = await operation.run(url=...)
```

## How it works

The HTTP protocol.

The HTTP *protocol* client is the same engine as the HTTP *connectivity*
client, exposed here under the protocol taxonomy because it speaks a
specific protocol rather than reaching a host.  The two share the
implementation deliberately: there is one HTTP client in NetForge, not two.

## See also

* [the `protocols` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
