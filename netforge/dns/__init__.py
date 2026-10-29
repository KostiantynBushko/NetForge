"""The DNS capability.

DNS covers two things in NetForge: resolving names, and diagnosing the
mail authentication policies that live in DNS.  Both are read-only, so
every operation in this package is declared at the safe risk level.
"""

from __future__ import annotations

from netforge.dns.diagnostics import (
    DmarcPolicy,
    DnsDiagnosticsOperation,
    SpfPolicy,
    SpfResult,
    evaluate_spf,
    is_aligned,
    organisational_domain,
    parse_dmarc,
    parse_spf,
)
from netforge.dns.resolver import DnsLookupOperation, DnsRecord, DnsResolver

__all__ = [
    "DmarcPolicy",
    "DnsDiagnosticsOperation",
    "DnsLookupOperation",
    "DnsRecord",
    "DnsResolver",
    "SpfPolicy",
    "SpfResult",
    "evaluate_spf",
    "is_aligned",
    "organisational_domain",
    "parse_dmarc",
    "parse_spf",
]
