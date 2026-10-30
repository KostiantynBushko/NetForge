# `dns.diagnostics`

> Analyse the SPF and DMARC policies of a domain.

**Risk:** Safe (level 1)  
**Category:** dns  
**Tags:** `dmarc`, `dns`, `email`, `policy`, `spf`  
**Implementation:** `netforge.dns.diagnostics:DnsDiagnosticsOperation`

---

## What it does

Fetches the SPF and DMARC records of a domain, parses them and reports what they say and what is missing. The analysis is read-only and touches nothing on the domain, so the operation is declared at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `domain` | string | — | **Required.** The domain to diagnose. (at least 1 character) |
| `sender_ip` | string | — | The IP address of the sender, for the SPF evaluation. |
| `spf_record` | string | — | The SPF record to analyse. Fetched from the DNS when omitted. |
| `dmarc_record` | string | — | The DMARC record to analyse. Fetched from the DNS when omitted. |
| `nameservers` | list of string | — | The resolvers to query. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `domain` | string | The domain that was diagnosed. |
| `spf` | object | The SPF policy of the domain. |
| `dmarc` | object | The DMARC policy of the domain. |
| `findings` | list of string | What the diagnostics found. |
| `score` | integer | The score of the domain, from 0 to 100. |

## Using it

### From the command line

```console
$ netforge run dns.diagnostics --domain <string>
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("dns.diagnostics")
result = await operation.run(domain=...)
```

## How it works

DNS diagnostics: SPF and DMARC.

The two policies that decide whether a domain is allowed to send mail in
its own name are worth a diagnostic of their own, and both of them are
*text*: a TXT record with a small, documented grammar.

So the analysis is written as pure functions over the record text.  They
can be checked against a policy that is pasted into a test, they need no
network and no resolver, and the same code serves the CLI, the REST API
and an agent.

The grammar is the one in RFC 7208 (SPF) and RFC 7489 (DMARC).

## See also

* [the `dns` package](README.md) — every operation it publishes
* [the architecture](../ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../README.md)
