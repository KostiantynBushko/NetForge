# `connectivity.http.request`

> Perform an HTTP request and report the status, headers and body.

**Risk:** Safe (level 1)  
**Category:** connectivity  
**Tags:** `http`, `https`, `request`  
**Implementation:** `netforge.connectivity.http:HttpRequestOperation`

---

## What it does

Performs an HTTP request and returns the status code, the response headers and the body. The body is truncated to the requested size so that a large download cannot flood an agent's context.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `url` | string | — | **Required.** The absolute URL to request. |
| `method` | string | `"GET"` | The HTTP method. |
| `headers` | object | — | Extra request headers. |
| `body` | string | — | Request body, sent as UTF-8. |
| `timeout` | number | — | Timeout in seconds. |
| `max_body_bytes` | integer | `1048576` | How many bytes of the body to keep in the response. (at least 0) |

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
| `reason` | string | The reason phrase that came with the status. |
| `headers` | object | The headers of the response. |
| `body` | string | The body of the response. |
| `body_bytes` | integer | How many bytes the body holds. |
| `truncated` | boolean | Whether the body was cut short. |
| `elapsed_ms` | number | How long the request took, in milliseconds. |

## Using it

### From the command line

```console
$ netforge run connectivity.http.request --url "..."
```

The values above are placeholders.  The request may also be given as a JSON object, which the flags are laid over:

```console
$ netforge run connectivity.http.request --request '{"url": "..."}'
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("connectivity.http.request")
result = await operation.run(url=...)
```

## How it works

HTTP connectivity.

The HTTP client is built on :mod:`urllib.request` from the standard
library and run in a worker thread, so the framework keeps exactly one
hard dependency -- Pydantic -- and the HTTP capability works on a bare
Python installation.

That is a deliberate trade.  ``httpx`` or ``requests`` would be more
convenient, but they are third-party, and the specification's "Framework
First" principle says the networking logic must not drag an ecosystem along
with it.

## See also

* [the `connectivity` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
