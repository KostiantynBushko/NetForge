"""TLS inspection.

Python's :mod:`ssl` module is enough to see what a TLS endpoint negotiates:
the protocol version, the cipher suite, the certificate and whether the
peer verified.  No third-party library is needed, and no third-party
library is used.

What is reported:

* the negotiated TLS version and the cipher suite;
* the certificate's subject, issuer, validity window and fingerprints;
* the certificate's SANs, when it carries any.

That is an assessment view of a certificate, not a validation of it.
"""

from __future__ import annotations

import asyncio
import hashlib
import ssl
import time
from dataclasses import dataclass, field

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["TlsInspectionOperation", "TlsReport", "inspect_tls"]

_logger = get_logger("security.tls")


@dataclass(slots=True)
class TlsReport:
    """What a TLS endpoint negotiated."""

    host: str
    port: int
    version: str = ""
    cipher: str = ""
    peer_certificate: dict[str, object] = field(default_factory=dict)
    subject_alternative_names: list[str] = field(default_factory=list)
    verified: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the report as a plain dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "version": self.version,
            "cipher": self.cipher,
            "peer_certificate": dict(self.peer_certificate),
            "subject_alternative_names": list(self.subject_alternative_names),
            "verified": self.verified,
            "error": self.error,
        }


def _describe_certificate(certificate: dict[str, object] | None) -> tuple[dict[str, object], list[str]]:
    """Turn the certificate mapping of :mod:`ssl` into a flat description."""
    if not certificate:
        return {}, []

    def _flatten(prefix: str, value: object) -> dict[str, object]:
        if not isinstance(value, tuple):
            return {prefix: value}
        return {
            f"{prefix}.{index}": item
            for index, item in enumerate(value)
            if item not in (None, b"")
        }

    described: dict[str, object] = {}
    for key, value in certificate.items():
        if key == "subjectAltName":
            continue
        described.update(_flatten(str(key), value))

    san_value = certificate.get("subjectAltName") or ()
    sans = [str(item) for item in san_value if str(item).startswith("DNS") or str(item).startswith("IP")]

    for digest_name, hasher in (("sha256", hashlib.sha256), ("sha1", hashlib.sha1)):
        der = certificate.get("der")
        if isinstance(der, bytes):
            described[f"fingerprint_{digest_name}"] = hasher(der).hexdigest()

    return described, sans


async def inspect_tls(
    host: str,
    port: int = 443,
    *,
    timeout: float = 5.0,
    verify: bool = False,
    server_hostname: str | None = None,
) -> TlsReport:
    """Connect to a TLS endpoint and report what it negotiated."""
    report = TlsReport(host=host, port=port)

    context = ssl.create_default_context()
    if not verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                host, port, ssl=context, server_hostname=server_hostname or host
            ),
            timeout=timeout,
        )
    except (ssl.SSLError, ssl.CertificateError) as exc:
        report.error = str(exc)
        return report
    except (OSError, asyncio.TimeoutError) as exc:
        report.error = str(exc)
        return report

    try:
        ssl_object = writer.get_extra_info("ssl_object")
        if ssl_object is not None:
            report.version = ssl_object.version() or ""
            cipher = ssl_object.cipher()
            report.cipher = cipher[0] if cipher else ""
            certificate = ssl_object.getpeercert()
            report.verified = bool(certificate)
            described, sans = _describe_certificate(certificate)
            report.peer_certificate = described
            report.subject_alternative_names = sans
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, asyncio.TimeoutError):  # pragma: no cover - best effort
            pass

    return report


class TlsInspectRequest(RequestModel):
    """Request of :class:`TlsInspectionOperation`."""

    host: str = Field(min_length=1, description="The host to inspect.")
    port: int = Field(default=443, ge=1, le=65535, description="The TLS port.")
    timeout: float | None = Field(default=5.0, gt=0.0, description="Connect timeout in seconds.")
    verify: bool = Field(default=False, description="Verify the certificate chain.")


class TlsInspectResponse(ResponseModel):
    """Response of :class:`TlsInspectionOperation`."""

    host: str = Field(description="The host that was inspected.")
    port: int = Field(description="The port that was inspected.")
    version: str = Field(default="", description="The TLS version that was negotiated.")
    cipher: str = Field(default="", description="The cipher that was negotiated.")
    peer_certificate: dict[str, object] = Field(default_factory=dict, description="The certificate the other end presented.")
    subject_alternative_names: list[str] = Field(default_factory=list, description="The alternative names of the certificate.")
    verified: bool = Field(default=False, description="Whether the certificate could be verified.")
    error: str | None = Field(default=None, description="Why the inspection failed, when it did.")


class TlsInspectionOperation(Operation[TlsInspectRequest, TlsInspectResponse]):
    """Inspect the TLS configuration of an endpoint."""

    name = "security.tls.inspect"
    category = CapabilityCategory.SECURITY
    risk_level = RiskLevel.SAFE
    summary = "Inspect the TLS version, the cipher and the certificate of an endpoint."
    description = (
        "Connects to a TLS endpoint and reports the negotiated protocol version, the "
        "cipher suite and the peer's certificate. It reads the endpoint's own answers "
        "and changes nothing, so the operation is declared at the safe level."
    )
    tags = frozenset({"tls", "ssl", "certificate", "inspection"})

    request_model = TlsInspectRequest
    response_model = TlsInspectResponse

    async def execute(
        self, request: TlsInspectRequest, context: ExecutionContext
    ) -> TlsInspectResponse:
        """Inspect the endpoint."""
        started = time.perf_counter()
        report = await inspect_tls(
            request.host,
            request.port,
            timeout=request.timeout or 5.0,
            verify=request.verify and context.config.verify_tls,
        )
        return TlsInspectResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            host=report.host,
            port=report.port,
            version=report.version,
            cipher=report.cipher,
            peer_certificate=report.peer_certificate,
            subject_alternative_names=report.subject_alternative_names,
            verified=report.verified,
            error=report.error,
        )
