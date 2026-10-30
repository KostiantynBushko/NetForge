# `security.tls.inspect`

> Inspect the TLS version, the cipher and the certificate of an endpoint.

**Risk:** Safe (level 1)  
**Category:** security  
**Tags:** `certificate`, `inspection`, `ssl`, `tls`  
**Implementation:** `netforge.security.tls:TlsInspectionOperation`

---

## What it does

Connects to a TLS endpoint and reports the negotiated protocol version, the cipher suite and the peer's certificate. It reads the endpoint's own answers and changes nothing, so the operation is declared at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `host` | string | — | **Required.** The host to inspect. (at least 1 character) |
| `port` | integer | `443` | The TLS port. (at least 1, at most 65535) |
| `timeout` | number | `5.0` | Connect timeout in seconds. |
| `verify` | boolean | `false` | Verify the certificate chain. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `host` | string | The host that was inspected. |
| `port` | integer | The port that was inspected. |
| `version` | string | The TLS version that was negotiated. |
| `cipher` | string | The cipher that was negotiated. |
| `peer_certificate` | object | The certificate the other end presented. |
| `subject_alternative_names` | list of string | The alternative names of the certificate. |
| `verified` | boolean | Whether the certificate could be verified. |
| `error` | string | Why the inspection failed, when it did. |

## Using it

### From the command line

```console
$ netforge run security.tls.inspect --host "..."
```

The values above are placeholders.  The request may also be given as a JSON object, which the flags are laid over:

```console
$ netforge run security.tls.inspect --request '{"host": "..."}'
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("security.tls.inspect")
result = await operation.run(host=...)
```

## How it works

TLS inspection.

Python's :mod:`ssl` module is enough to see what a TLS endpoint negotiates:
the protocol version, the cipher suite, the certificate and whether the
peer verified.  No third-party library is needed, and no third-party
library is used.

What is reported:

* the negotiated TLS version and the cipher suite;
* the certificate's subject, issuer, validity window and fingerprints;
* the certificate's SANs, when it carries any.

That is an assessment view of a certificate, not a validation of it.

## See also

* [the `security` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
