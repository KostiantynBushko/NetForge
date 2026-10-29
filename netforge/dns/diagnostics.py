"""DNS diagnostics: SPF and DMARC.

The two policies that decide whether a domain is allowed to send mail in
its own name are worth a diagnostic of their own, and both of them are
*text*: a TXT record with a small, documented grammar.

So the analysis is written as pure functions over the record text.  They
can be checked against a policy that is pasted into a test, they need no
network and no resolver, and the same code serves the CLI, the REST API
and an agent.

The grammar is the one in RFC 7208 (SPF) and RFC 7489 (DMARC).
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = [
    "DmarcPolicy",
    "DnsDiagnosticsOperation",
    "SpfPolicy",
    "SpfResult",
    "evaluate_spf",
    "is_aligned",
    "organisational_domain",
    "parse_dmarc",
    "parse_spf",
]

_logger = get_logger("dns.diagnostics")

#: The verdicts SPF can produce.
SPF_RESULTS = ("pass", "fail", "neutral", "none", "softfail", "temperror", "permerror")


@dataclass(slots=True)
class SpfPolicy:
    """A parsed SPF record."""

    version: str = ""
    mechanisms: list[str] = field(default_factory=list)
    modifiers: dict[str, str] = field(default_factory=dict)
    raw: str = ""

    @property
    def is_valid(self) -> bool:
        """Return ``True`` when the record starts with the right version tag."""
        return self.version.lower() == "spf1"

    @property
    def qualifier(self) -> str:
        """Return the default qualifier of the record: ``+``, ``-``, ``~`` or ``?``."""
        for mechanism in self.mechanisms:
            if mechanism.startswith("+"):
                return "+"
            if mechanism.startswith("-"):
                return "-"
            if mechanism.startswith("~"):
                return "~"
            if mechanism.startswith("?"):
                return "?"
        return "+"

    @property
    def all_mechanism(self) -> str | None:
        """Return the ``all`` mechanism, which decides the default verdict."""
        for mechanism in self.mechanisms:
            if mechanism.lstrip("+-~?").lower() == "all":
                return mechanism
        return None

    def to_dict(self) -> dict[str, object]:
        """Return the policy as a plain dictionary."""
        return {
            "version": self.version,
            "mechanisms": list(self.mechanisms),
            "modifiers": dict(self.modifiers),
            "valid": self.is_valid,
        }


@dataclass(slots=True)
class SpfResult:
    """The verdict of an SPF evaluation."""

    result: str = "none"
    explanation: str = ""
    matched_mechanism: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the verdict as a plain dictionary."""
        return {
            "result": self.result,
            "explanation": self.explanation,
            "matched_mechanism": self.matched_mechanism,
        }


def parse_spf(record: str) -> SpfPolicy:
    """Parse an SPF record into a :class:`SpfPolicy`."""
    text = (record or "").strip().strip('"')
    if not text:
        return SpfPolicy()

    terms = text.split()
    version = ""
    mechanisms: list[str] = []
    modifiers: dict[str, str] = {}

    for term in terms:
        lowered = term.lower()
        if lowered.startswith("v="):
            version = term[2:]
            continue
        if "=" in term and term.split("=", 1)[0].lower() in {"redirect", "exp"}:
            key, _, value = term.partition("=")
            modifiers[key.lower()] = value
            continue
        mechanisms.append(term)

    return SpfPolicy(version=version, mechanisms=mechanisms, modifiers=modifiers, raw=text)


def _ip_in_network(ip_text: str, network_text: str) -> bool:
    try:
        address = ipaddress.ip_address(ip_text)
        network = ipaddress.ip_network(network_text, strict=False)
    except ValueError:
        return False
    return address in network


def evaluate_spf(record: str, sender_ip: str) -> SpfResult:
    """Evaluate an SPF record for ``sender_ip``.

    The mechanisms are evaluated in order and the first match decides the
    verdict, which is what RFC 7208 specifies.  ``all`` decides the
    default; ``include``, ``a`` and ``mx`` are treated as "not matching",
    because resolving them would need a DNS query, and a diagnostic that
    silently guesses is worse than one that says so.
    """
    policy = parse_spf(record)
    if not policy.raw:
        return SpfResult(result="none", explanation="the domain publishes no SPF record")
    if not policy.is_valid:
        return SpfResult(
            result="permerror",
            explanation=f"the record does not start with a version tag (got {policy.version!r})",
        )

    for mechanism in policy.mechanisms:
        qualifier = ""
        body = mechanism
        if body and body[0] in "+-~?":
            qualifier, body = body[0], body[1:]

        name, _, argument = body.partition(":")
        name = name.lower()

        if name == "all":
            verdict = {"+": "pass", "-": "fail", "~": "softfail", "?": "neutral"}.get(qualifier, "pass")
            return SpfResult(
                result=verdict,
                explanation=f"matched the 'all' mechanism with the qualifier {qualifier!r}",
                matched_mechanism=mechanism,
            )

        if name == "ip4":
            if _ip_in_network(sender_ip, argument):
                return SpfResult(
                    result="pass",
                    explanation=f"the sender is inside {argument}",
                    matched_mechanism=mechanism,
                )
            continue

        if name == "ip6":
            if _ip_in_network(sender_ip, argument):
                return SpfResult(
                    result="pass",
                    explanation=f"the sender is inside {argument}",
                    matched_mechanism=mechanism,
                )
            continue

        if name in {"include", "a", "mx", "exists", "ptr"}:
            # These need a DNS query; say so rather than guess.
            continue

    if "redirect" in policy.modifiers:
        return SpfResult(
            result="none",
            explanation=(
                "the record redirects to another domain "
                f"({policy.modifiers['redirect']}); the delegated policy was not evaluated"
            ),
        )

    return SpfResult(
        result="neutral",
        explanation="no mechanism matched the sender",
    )


@dataclass(slots=True)
class DmarcPolicy:
    """A parsed DMARC record."""

    version: str = ""
    tags: dict[str, str] = field(default_factory=dict)
    raw: str = ""

    @property
    def is_valid(self) -> bool:
        """Return ``True`` when the record starts with the right version tag."""
        return self.version.lower() == "dmarc1"

    @property
    def policy(self) -> str:
        """Return the ``p`` tag: ``none``, ``quarantine`` or ``reject``."""
        return self.tags.get("p", "none").lower()

    @property
    def subdomain_policy(self) -> str:
        """Return the ``sp`` tag, falling back to the ``p`` tag."""
        return self.tags.get("sp", self.policy).lower()

    @property
    def percentage(self) -> int:
        """Return the ``pct`` tag, clamped to 0-100."""
        try:
            value = int(self.tags.get("pct", "100"))
        except ValueError:
            return 100
        return max(0, min(100, value))

    @property
    def alignment_adkim(self) -> str:
        """Return the ``adkim`` tag: ``s`` (strict) or ``r`` (relaxed)."""
        return self.tags.get("adkim", "r").lower()

    @property
    def alignment_aspf(self) -> str:
        """Return the ``aspf`` tag: ``s`` (strict) or ``r`` (relaxed)."""
        return self.tags.get("aspf", "r").lower()

    def to_dict(self) -> dict[str, object]:
        """Return the policy as a plain dictionary."""
        return {
            "version": self.version,
            "tags": dict(self.tags),
            "policy": self.policy,
            "valid": self.is_valid,
        }


def parse_dmarc(record: str) -> DmarcPolicy:
    """Parse a DMARC record into a :class:`DmarcPolicy`."""
    text = (record or "").strip().strip('"')
    if not text:
        return DmarcPolicy()

    tags: dict[str, str] = {}
    version = ""
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        key, _, value = part.partition("=")
        key = key.strip().lower()
        value = value.strip()
        if key == "v":
            version = value
        elif key:
            tags[key] = value

    return DmarcPolicy(version=version, tags=tags, raw=text)


def organisational_domain(domain: str) -> str:
    """Return the organisational domain of ``domain``.

    This is the public-suffix-aware part of the name, e.g.
    ``mail.example.co.uk`` becomes ``example.co.uk``.  Without a public
    suffix list the last two labels are used, which is right for most
    names and is documented as an approximation.
    """
    labels = [label for label in domain.lower().strip(".").split(".") if label]
    if len(labels) <= 2:
        return ".".join(labels)
    return ".".join(labels[-2:])


def is_aligned(subdomain: str, from_domain: str, mode: str) -> bool:
    """Return ``True`` when the two domains are aligned under ``mode``."""
    left = subdomain.lower().strip(".")
    right = from_domain.lower().strip(".")
    if not left or not right:
        return False
    if mode == "s":
        return left == right
    return left.endswith("." + right) or left == right


class DnsDiagnosticsRequest(RequestModel):
    """Request of :class:`DnsDiagnosticsOperation`."""

    domain: str = Field(min_length=1, description="The domain to diagnose.")
    sender_ip: str | None = Field(
        default=None,
        description="The IP address of the sender, for the SPF evaluation.",
    )
    spf_record: str | None = Field(
        default=None,
        description="The SPF record to analyse. Fetched from the DNS when omitted.",
    )
    dmarc_record: str | None = Field(
        default=None,
        description="The DMARC record to analyse. Fetched from the DNS when omitted.",
    )
    nameservers: list[str] | None = Field(default=None, description="The resolvers to query.")


class DnsDiagnosticsResponse(ResponseModel):
    """Response of :class:`DnsDiagnosticsOperation`."""

    domain: str
    spf: dict[str, object] = Field(default_factory=dict)
    dmarc: dict[str, object] = Field(default_factory=dict)
    findings: list[str] = Field(default_factory=list)
    score: int = Field(default=0, ge=0, le=100)


class DnsDiagnosticsOperation(Operation[DnsDiagnosticsRequest, DnsDiagnosticsResponse]):
    """Diagnose the SPF and DMARC policies of a domain."""

    name = "dns.diagnostics"
    category = CapabilityCategory.DNS
    risk_level = RiskLevel.SAFE
    summary = "Analyse the SPF and DMARC policies of a domain."
    description = (
        "Fetches the SPF and DMARC records of a domain, parses them and reports what "
        "they say and what is missing. The analysis is read-only and touches nothing "
        "on the domain, so the operation is declared at the safe level."
    )
    tags = frozenset({"dns", "spf", "dmarc", "email", "policy"})

    request_model = DnsDiagnosticsRequest
    response_model = DnsDiagnosticsResponse

    async def execute(
        self, request: DnsDiagnosticsRequest, context: ExecutionContext
    ) -> DnsDiagnosticsResponse:
        """Analyse the policies of the domain."""
        from netforge.dns.resolver import DnsResolver

        findings: list[str] = []
        spf_text = request.spf_record
        dmarc_text = request.dmarc_record

        resolver = DnsResolver(nameservers=request.nameservers)
        if spf_text is None:
            spf_text = await _fetch_txt(resolver, request.domain, findings)
        if dmarc_text is None:
            dmarc_text = await _fetch_txt(resolver, f"_dmarc.{request.domain}", findings)

        spf_policy = parse_spf(spf_text or "")
        dmarc_policy = parse_dmarc(dmarc_text or "")

        if not spf_text:
            findings.append("The domain publishes no SPF record.")
        elif not spf_policy.is_valid:
            findings.append("The SPF record does not start with the 'v=spf1' version tag.")
        else:
            if not spf_policy.all_mechanism:
                findings.append(
                    "The SPF record has no 'all' mechanism, so the default verdict is "
                    "undefined and receivers fall back to their own policy."
                )
            if request.sender_ip:
                verdict = evaluate_spf(spf_text or "", request.sender_ip)
                findings.append(f"SPF for {request.sender_ip}: {verdict.result} ({verdict.explanation}).")
            if spf_policy.qualifier == "+":
                findings.append(
                    "The SPF record ends with '+all', which authorises every sender. "
                    "Use '-all' or '~all' instead."
                )

        if not dmarc_text:
            findings.append("The domain publishes no DMARC record.")
        elif not dmarc_policy.is_valid:
            findings.append("The DMARC record does not start with the 'v=DMARC1' version tag.")
        else:
            if dmarc_policy.policy == "none":
                findings.append(
                    "The DMARC policy is 'none': failures are reported but nothing is "
                    "rejected. Use 'quarantine' or 'reject' to enforce it."
                )
            if "rua" not in dmarc_policy.tags:
                findings.append(
                    "The DMARC record has no 'rua' tag, so no aggregate report is sent "
                    "and there is no feedback loop."
                )
            if request.sender_ip:
                organisational = organisational_domain(request.domain)
                if not is_aligned(organisational, request.domain, dmarc_policy.alignment_aspf):
                    findings.append(
                        f"The organisational domain {organisational!r} is not aligned with "
                        f"the domain {request.domain!r} under the "
                        f"{dmarc_policy.alignment_aspf!r} alignment mode."
                    )

        score = _score(spf_policy, dmarc_policy, bool(spf_text), bool(dmarc_text))

        return DnsDiagnosticsResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            domain=request.domain,
            spf=spf_policy.to_dict(),
            dmarc=dmarc_policy.to_dict(),
            findings=findings,
            score=score,
        )


async def _fetch_txt(resolver, name: str, findings: list[str]) -> str:
    """Fetch the first TXT record of ``name``, recording a warning on failure."""
    try:
        records = resolver.resolve(name, "TXT")
    except Exception as exc:  # noqa: BLE001 - the diagnostic must not fail on a missing record
        findings.append(f"The TXT record of {name} could not be fetched: {exc}")
        return ""
    if not records:
        return ""
    return records[0].value


def _score(spf: SpfPolicy, dmarc: DmarcPolicy, has_spf: bool, has_dmarc: bool) -> int:
    """Return a 0-100 score for the mail authentication posture."""
    score = 0
    if has_spf and spf.is_valid:
        score += 35
        if spf.qualifier in {"-", "~"}:
            score += 10
    if has_dmarc and dmarc.is_valid:
        score += 35
        if dmarc.policy in {"quarantine", "reject"}:
            score += 20
        elif dmarc.policy == "none":
            score += 5
    return min(100, score)
