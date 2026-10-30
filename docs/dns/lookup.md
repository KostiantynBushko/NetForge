# `dns.lookup`

> Resolve a DNS name and return its records.

**Risk:** Safe (level 1)  
**Category:** dns  
**Tags:** `dns`, `lookup`, `resolve`  
**Implementation:** `netforge.dns.resolver:DnsLookupOperation`

---

## What it does

Resolves a DNS name and returns the records that were found. Address records are resolved with the system's own resolver; the other record types need the optional dnspython extra.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `name` | string | — | **Required.** The name to resolve. (at least 1 character) |
| `record_type` | string | `"A"` | The record type to look for. |
| `nameservers` | list of string | — | The resolvers to query. |
| `timeout` | number | `5.0` | Query timeout in seconds. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `name` | string | The name that was resolved. |
| `record_type` | string | The kind of record that was asked for. |
| `records` | list of object | The records that came back. |
| `addresses` | list of string | The addresses the name resolves to. |
| `count` | integer | How many records came back. |

## Using it

### From the command line

```console
$ netforge run dns.lookup --name <string>
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("dns.lookup")
result = await operation.run(name=...)
```

## How it works

DNS resolution.

Address records are resolved with :func:`socket.getaddrinfo`, which is in
the standard library and uses the system's own resolver -- including
``/etc/hosts``, ``/etc/nsswitch.conf`` and the local caching resolver.

The other record types (MX, NS, TXT, SOA, CNAME) need a real DNS query,
and :mod:`dnspython` is the optional extra that provides one.  It is
imported lazily: the capability is *listed* on a machine without it, and
running it there reports exactly what to install.

## See also

* [the `dns` package](README.md) — every operation it publishes
* [the architecture](../ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../README.md)
