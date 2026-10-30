# `security.headers.analyze`

> Analyse the security headers of an HTTP response.

**Risk:** Safe (level 1)  
**Category:** security  
**Tags:** `hardening`, `headers`, `http`, `security`  
**Implementation:** `netforge.security.headers:HttpHeaderAnalysisOperation`

---

## What it does

Checks a set of HTTP response headers against the security headers that should be there and reports what is missing and why it matters. The headers can be supplied directly or fetched from a URL. The analysis is read-only, so the operation is declared at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `headers` | object | — | The headers to analyse. |
| `url` | string | — | Fetch the headers from this URL instead. |
| `timeout` | number | `10.0` | Timeout in seconds. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `findings` | list of object | The problems that were found. |
| `score` | integer | The score of the headers, from 0 to 100. |
| `checked` | integer | The headers that were checked. |
| `present` | integer | The headers that were present. |
| `url` | string | The URL the headers came from. |

## Using it

### From the command line

```console
$ netforge run security.headers.analyze
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("security.headers.analyze")
result = await operation.run()
```

## How it works

HTTP security header analysis.

The analysis is a pure function over a header mapping, so it can be run
against a captured response, a fixture, or a live endpoint -- and it always
gives the same answer for the same headers.

The checks are the ones that matter in practice:

* **HSTS** -- is the connection pinned to TLS?
* **Content-Security-Policy** -- is the page allowed to load scripts?
* **X-Content-Type-Options** -- can a browser be tricked into
  interpreting a download as HTML?
* **X-Frame-Options** / **frame-ancestors** -- can the page be framed?
* **Referrer-Policy** -- how much of the URL leaks to a third party?
* **Cookie** -- do the cookies carry ``Secure`` and ``HttpOnly``?

## See also

* [the `security` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
