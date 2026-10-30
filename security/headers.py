"""HTTP security header analysis.

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
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from pydantic import Field

from netforge.connectivity.http import HttpConnection
from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = [
    "HttpHeaderAnalysisOperation",
    "HeaderFinding",
    "SECURITY_HEADERS",
    "analyze_headers",
    "analyze_set_cookie",
]

_logger = get_logger("security.headers")

#: The headers that are checked, and what their absence means.
SECURITY_HEADERS: dict[str, str] = {
    "strict-transport-security": "The connection is not pinned to TLS with HSTS.",
    "content-security-policy": "No Content-Security-Policy limits what the page may load.",
    "x-content-type-options": "A download can be interpreted as HTML by the browser.",
    "x-frame-options": "The page can be framed by another site (clickjacking).",
    "referrer-policy": "The full URL may leak to third parties.",
    "permissions-policy": "The browser features the page may use are not restricted.",
    "cross-origin-opener-policy": "The page can be opened by a cross-origin window.",
}


@dataclass(slots=True)
class HeaderFinding:
    """One finding of the header analysis."""

    severity: str
    header: str
    message: str
    present: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return the finding as a plain dictionary."""
        return {
            "severity": self.severity,
            "header": self.header,
            "message": self.message,
            "present": self.present,
        }


def _lower(headers: dict[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def analyze_set_cookie(value: str) -> list[str]:
    """Return the problems with a ``Set-Cookie`` header value."""
    problems: list[str] = []
    lowered = value.lower()
    if "secure" not in lowered:
        problems.append("the cookie is not marked 'Secure' and will travel over plain HTTP.")
    if "httponly" not in lowered:
        problems.append("the cookie is not marked 'HttpOnly' and is readable from JavaScript.")
    if "samesite" not in lowered:
        problems.append("the cookie carries no 'SameSite' attribute.")
    return problems


def analyze_headers(headers: dict[str, str]) -> list[HeaderFinding]:
    """Analyse a response's headers and report what is missing."""
    lowered = _lower(headers)
    findings: list[HeaderFinding] = []

    for header, consequence in SECURITY_HEADERS.items():
        if header in lowered:
            findings.append(
                HeaderFinding(
                    severity="info",
                    header=header,
                    message=f"the header is present: {lowered[header][:200]}",
                    present=True,
                )
            )
        else:
            findings.append(
                HeaderFinding(
                    severity="warning",
                    header=header,
                    message=consequence,
                    present=False,
                )
            )

    server = lowered.get("server")
    if server:
        findings.append(
            HeaderFinding(
                severity="info",
                header="server",
                message=f"the server discloses its software: {server}",
                present=True,
            )
        )

    for key, value in headers.items():
        if str(key).lower() == "set-cookie":
            for problem in analyze_set_cookie(str(value)):
                findings.append(
                    HeaderFinding(
                        severity="warning",
                        header="set-cookie",
                        message=problem,
                        present=True,
                    )
                )

    return findings


class HttpHeaderAnalysisRequest(RequestModel):
    """Request of :class:`HttpHeaderAnalysisOperation`."""

    headers: dict[str, str] = Field(default_factory=dict, description="The headers to analyse.")
    url: str | None = Field(default=None, description="Fetch the headers from this URL instead.")
    timeout: float | None = Field(default=10.0, gt=0.0, description="Timeout in seconds.")


class HttpHeaderAnalysisResponse(ResponseModel):
    """Response of :class:`HttpHeaderAnalysisOperation`."""

    findings: list[dict[str, object]] = Field(default_factory=list, description="The problems that were found.")
    score: int = Field(default=0, description="The score of the headers, from 0 to 100.")
    checked: int = Field(default=0, description="The headers that were checked.")
    present: int = Field(default=0, description="The headers that were present.")
    url: str | None = Field(default=None, description="The URL the headers came from.")


class HttpHeaderAnalysisOperation(Operation[HttpHeaderAnalysisRequest, HttpHeaderAnalysisResponse]):
    """Analyse the security headers of an HTTP response."""

    name = "security.headers.analyze"
    category = CapabilityCategory.SECURITY
    risk_level = RiskLevel.SAFE
    summary = "Analyse the security headers of an HTTP response."
    description = (
        "Checks a set of HTTP response headers against the security headers that "
        "should be there and reports what is missing and why it matters. The headers "
        "can be supplied directly or fetched from a URL. The analysis is read-only, so "
        "the operation is declared at the safe level."
    )
    tags = frozenset({"http", "headers", "security", "hardening"})

    request_model = HttpHeaderAnalysisRequest
    response_model = HttpHeaderAnalysisResponse

    async def execute(
        self, request: HttpHeaderAnalysisRequest, context: ExecutionContext
    ) -> HttpHeaderAnalysisResponse:
        """Analyse the headers."""
        started = time.perf_counter()
        headers = dict(request.headers)
        url = request.url

        if request.url and not headers:
            client = HttpConnection(
                timeout=request.timeout if request.timeout is not None else context.timeout,
                verify_tls=context.config.verify_tls,
                user_agent=context.config.user_agent,
            )
            try:
                response = await client.request(request.url, method="HEAD")
                headers = dict(response.headers)
            except (ConnectionError, TimeoutError, OSError) as exc:
                return HttpHeaderAnalysisResponse(
                    operation=self.name,
                    risk_level=self.risk_level.label,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    findings=[],
                    url=request.url,
                    warnings=[f"the headers could not be fetched: {exc}"],
                )

        findings = analyze_headers(headers)
        present = sum(1 for finding in findings if finding.present and finding.header in SECURITY_HEADERS)
        checked = len(SECURITY_HEADERS)
        score = int(round(100 * present / checked)) if checked else 0

        return HttpHeaderAnalysisResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            findings=[finding.to_dict() for finding in findings],
            score=score,
            checked=checked,
            present=present,
            url=url,
        )
