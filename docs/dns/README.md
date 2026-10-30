# `netforge.dns`

DNS covers two things in NetForge: resolving names, and diagnosing the
mail authentication policies that live in DNS.

Both are read-only, so every operation in this package is declared at the
safe risk level.

---

## Operations

<!-- generated:operations -->
| Operation | Risk | What it does |
|---|---|---|
| [`dns.diagnostics`](diagnostics.md) | Safe | Analyse the SPF and DMARC policies of a domain. |
| [`dns.lookup`](lookup.md) | Safe | Resolve a DNS name and return its records. |
<!-- /generated:operations -->

---

## Resolution

`DnsResolver(*, nameservers=None, timeout=5.0)` resolves records for a
name. `DnsRecord` is one record: `name`, `type`, `value`, `ttl`,
`priority` and `metadata`.

Address records (`A`, `AAAA`) are resolved with `socket.getaddrinfo`,
which is in the standard library and uses the system's own resolver —
including `/etc/hosts`, `/etc/nsswitch.conf` and the local caching
resolver.

The other record types (MX, NS, TXT, SOA, CNAME) need a real DNS query,
and `dnspython` is the optional extra that provides one.

### The dnspython extra

The `dns` extra provides `dnspython`. When it is missing, the capability
is still *listed*, and running it reports exactly what to install:

<!-- generated:public-api -->
```text
class DmarcPolicy(version: str = '', tags: dict[str, str] = <factory>, raw: str = '')
class DnsDiagnosticsOperation()
class DnsLookupOperation()
class DnsRecord(name: str, type: str, value: str, ttl: int | None = None, priority: int | None = None, metadata: dict[str, str] = <factory>)
class DnsResolver(*, nameservers: list[str] | None = None, timeout: float = 5.0)
class SpfPolicy(version: str = '', mechanisms: list[str] = <factory>, modifiers: dict[str, str] = <factory>, raw: str = '')
class SpfResult(result: str = 'none', explanation: str = '', matched_mechanism: str | None = None)
def evaluate_spf(record: str, sender_ip: str) -> SpfResult
def is_aligned(subdomain: str, from_domain: str, mode: str) -> bool
def organisational_domain(domain: str) -> str
def parse_dmarc(record: str) -> DmarcPolicy
def parse_spf(record: str) -> SpfPolicy
```
<!-- /generated:public-api -->

dnspython is located through its installed distribution and bound under
the `dns` name explicitly, so NetForge's own `dns` capability package can
never shadow it — which matters when NetForge runs from a checkout, where
the project root is on `sys.path`.

---

## The mail diagnostics

This half of the package is pure text processing, and it is the part worth
having exactly right.

### SPF

`parse_spf(record)` returns an `SpfPolicy`: `version`, `mechanisms`,
`modifiers` and the `raw` record.

`evaluate_spf(record, sender_ip)` returns an `SpfResult`: `result`
(`pass`, `fail`, `neutral`, `none`, `softfail`, `permerror`, `temperror`),
an `explanation` in words, and the `matched_mechanism`.

### DMARC

`parse_dmarc(record)` returns a `DmarcPolicy`: `version`, `tags` and the
`raw` record.

### Alignment

`is_aligned(subdomain, from_domain, mode)` answers the alignment
question under `relaxed` or `strict` mode.

`organisational_domain(domain)` returns the organisational domain — the
domain a policy is actually written against, as opposed to the subdomain
the mail came from.

---

## Using it

```python
from netforge.dns import evaluate_spf, is_aligned, parse_spf

policy = parse_spf("v=spf1 ip4:192.0.2.0/24 include:example.com -all")
verdict = evaluate_spf(policy.raw, "198.51.100.7")

print(verdict.result)            # 'pass'
print(verdict.matched_mechanism)  # 'ip4:192.0.2.0/24'
print(is_aligned("mail.example.com", "example.com", "relaxed"))  # True
```

Through the framework:

```python
operation = registry.create("dns.lookup")
result = await operation.run(name="example.com", record_type="MX")
```

---

## The public API

```text
class DmarcPolicy                       (version='', tags={}, raw='')
class DnsDiagnosticsOperation
class DnsLookupOperation
class DnsRecord                         (name, type, value, ttl=None,
                                         priority=None, metadata={})
class DnsResolver                       (*, nameservers=None, timeout=5.0)
class SpfPolicy                         (version='', mechanisms=[], modifiers={}, raw='')
class SpfResult                         (result='none', explanation='',
                                         matched_mechanism=None)

evaluate_spf(record, sender_ip) -> SpfResult
is_aligned(subdomain, from_domain, mode) -> bool
organisational_domain(domain) -> str
parse_dmarc(record) -> DmarcPolicy
parse_spf(record) -> SpfPolicy
```

---

## Notes

* The SPF and DMARC parsers never touch the network. They are pure
  functions over a record, so they can be tested against a captured sample
  — which is exactly what the test suite does.
* A missing `dnspython` degrades one capability; it never breaks the
  import of the package or the framework.
* See also: [the architecture](../ARCHITECTURE.md),
  [configuration.md](../configuration/README.md).
