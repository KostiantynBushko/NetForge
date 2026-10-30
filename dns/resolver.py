"""DNS resolution.

Address records are resolved with :func:`socket.getaddrinfo`, which is in
the standard library and uses the system's own resolver -- including
``/etc/hosts``, ``/etc/nsswitch.conf`` and the local caching resolver.

The other record types (MX, NS, TXT, SOA, CNAME) need a real DNS query,
and :mod:`dnspython` is the optional extra that provides one.  It is
imported lazily: the capability is *listed* on a machine without it, and
running it there reports exactly what to install.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import socket
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.exceptions import DependencyMissingError
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = [
    "DnsLookupOperation",
    "DnsRecord",
    "DnsResolver",
    "ADDRESS_RECORD_TYPES",
    "DNS_EXTRA",
]

_logger = get_logger("dns.resolver")

DNS_EXTRA = "dns"

#: The record types the standard-library resolver can answer.
ADDRESS_RECORD_TYPES = ("A", "AAAA")


@dataclass(slots=True)
class DnsRecord:
    """One DNS record."""

    name: str
    type: str
    value: str
    ttl: int | None = None
    priority: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return the record as a plain dictionary."""
        data: dict[str, object] = {
            "name": self.name,
            "type": self.type,
            "value": self.value,
        }
        if self.ttl is not None:
            data["ttl"] = self.ttl
        if self.priority is not None:
            data["priority"] = self.priority
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data


def _dnspython_package_dir() -> Path:
    """Return the directory of dnspython's ``dns`` package.

    The distribution is located through the installed metadata rather than
    through ``sys.path``, so the answer does not depend on what happens to
    shadow the name.
    """
    try:
        distribution = importlib.metadata.distribution("dnspython")
    except importlib.metadata.PackageNotFoundError as exc:  # pragma: no cover
        raise DependencyMissingError(
            "dnspython",
            extra=DNS_EXTRA,
            feature="DNS record resolution",
        ) from exc
    return Path(distribution.locate_file("dns"))


def _bind_dnspython(package_dir: Path) -> None:
    """Bind dnspython's ``dns`` package under the top-level name.

    NetForge has a capability package called ``dns`` and dnspython ships a
    package with the same name.  When the project root is on ``sys.path`` --
    which is the case whenever NetForge runs from a checkout -- the local one
    wins, and a plain ``import dns.resolver`` hands back NetForge's own
    module rather than dnspython's.

    So dnspython's package is bound under that name explicitly, replacing
    whatever shadowed it.  Its submodules are then imported from dnspython,
    because the bound package is what the import machinery resolves them
    against.
    """
    existing = sys.modules.get("dns")
    if existing is not None:
        origin = getattr(existing, "__file__", None)
        if origin is not None and Path(origin).resolve().parent == package_dir.resolve():
            return  # already bound to dnspython

    # Drop the shadow, and anything that was imported through it.
    for name in [n for n in sys.modules if n == "dns" or n.startswith("dns.")]:
        del sys.modules[name]

    spec = importlib.util.spec_from_file_location(
        "dns",
        package_dir / "__init__.py",
        submodule_search_locations=[str(package_dir)],
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise DependencyMissingError(
            "dnspython",
            extra=DNS_EXTRA,
            feature="DNS record resolution",
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dns"] = module
    try:
        spec.loader.exec_module(module)
    except Exception:  # pragma: no cover - defensive
        del sys.modules["dns"]
        raise


def _load_dnspython():
    """Return dnspython's resolver module.

    dnspython is located through its installed distribution and bound under
    the ``dns`` name, so NetForge's own ``dns`` capability package can never
    shadow it -- see :func:`_bind_dnspython`.
    """
    _bind_dnspython(_dnspython_package_dir())

    import dns.resolver

    return dns.resolver


class DnsResolver:
    """Resolves DNS records for a name."""

    def __init__(self, *, nameservers: list[str] | None = None, timeout: float = 5.0) -> None:
        self.nameservers = list(nameservers) if nameservers else None
        self.timeout = timeout

    def _resolver(self):
        resolver_module = _load_dnspython()
        resolver = resolver_module.Resolver()
        if self.nameservers:
            resolver.nameservers = self.nameservers
        resolver.timeout = self.timeout
        resolver.lifetime = self.timeout
        return resolver

    def resolve_addresses(self, name: str) -> list[DnsRecord]:
        """Resolve the A and AAAA records of ``name`` with the system resolver."""
        records: list[DnsRecord] = []
        try:
            infos = socket.getaddrinfo(name, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise OSError(f"{name!r} could not be resolved: {exc}") from exc

        seen: set[str] = set()
        for info in infos:
            address = info[4][0]
            if address in seen:
                continue
            seen.add(address)
            records.append(
                DnsRecord(
                    name=name,
                    type="AAAA" if info[0] == socket.AF_INET6 else "A",
                    value=address,
                )
            )
        return records

    def resolve(self, name: str, record_type: str = "A") -> list[DnsRecord]:
        """Resolve ``record_type`` records for ``name``."""
        wanted = record_type.strip().upper()
        if wanted in ADDRESS_RECORD_TYPES:
            return self.resolve_addresses(name)

        resolver = self._resolver()
        answer = resolver.resolve(name, wanted)
        records: list[DnsRecord] = []
        for item in answer:
            value = item.to_text()
            priority = getattr(item, "preference", None)
            records.append(
                DnsRecord(
                    name=name,
                    type=wanted,
                    value=value,
                    ttl=getattr(item, "ttl", None),
                    priority=int(priority) if priority is not None else None,
                )
            )
        return records


class DnsLookupRequest(RequestModel):
    """Request of :class:`DnsLookupOperation`."""

    name: str = Field(min_length=1, description="The name to resolve.")
    record_type: str = Field(default="A", description="The record type to look for.")
    nameservers: list[str] | None = Field(default=None, description="The resolvers to query.")
    timeout: float | None = Field(default=5.0, gt=0.0, description="Query timeout in seconds.")


class DnsLookupResponse(ResponseModel):
    """Response of :class:`DnsLookupOperation`."""

    name: str
    record_type: str
    records: list[dict[str, object]] = Field(default_factory=list)
    addresses: list[str] = Field(default_factory=list)
    count: int = 0


class DnsLookupOperation(Operation[DnsLookupRequest, DnsLookupResponse]):
    """Resolve a DNS name."""

    name = "dns.lookup"
    category = CapabilityCategory.DNS
    risk_level = RiskLevel.SAFE
    summary = "Resolve a DNS name and return its records."
    description = (
        "Resolves a DNS name and returns the records that were found. Address records are "
        "resolved with the system's own resolver; the other record types need the "
        "optional dnspython extra."
    )
    tags = frozenset({"dns", "lookup", "resolve"})

    request_model = DnsLookupRequest
    response_model = DnsLookupResponse

    async def execute(
        self, request: DnsLookupRequest, context: ExecutionContext
    ) -> DnsLookupResponse:
        """Resolve the name."""
        resolver = DnsResolver(
            nameservers=request.nameservers,
            timeout=request.timeout or 5.0,
        )
        started = time.perf_counter()
        try:
            records = resolver.resolve(request.name, request.record_type)
        except DependencyMissingError as exc:
            return DnsLookupResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                name=request.name,
                record_type=request.record_type,
                records=[],
                addresses=[],
                count=0,
                warnings=[str(exc)],
            )
        except (OSError, ValueError) as exc:
            return DnsLookupResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                name=request.name,
                record_type=request.record_type,
                records=[],
                addresses=[],
                count=0,
                warnings=[f"the name could not be resolved: {exc}"],
            )

        addresses = [record.value for record in records if record.type in ADDRESS_RECORD_TYPES]
        return DnsLookupResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            name=request.name,
            record_type=request.record_type.strip().upper(),
            records=[record.to_dict() for record in records],
            addresses=addresses,
            count=len(records),
        )
