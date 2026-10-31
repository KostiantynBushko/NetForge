"""Security assessment.

The focus here is assessment and diagnostics, not exploitation.  The four
capabilities are:

* **scanner** -- which TCP ports are open, and how quickly they answer;
* **banner** -- what is answering, and what does it say about itself;
* **tls** -- what a TLS endpoint negotiates, and what its certificate says;
* **headers** -- what an HTTP response's security headers say.

The first two are observable, so they sit at level 2.  The last two are
read-only inspections of a service's own answers, so they sit at level 1.

A port scanner is not declared at the safe level even though it only opens
and closes a connection: a full sweep of a subnet is *visible* to the
target, and the risk model is about what the other side notices.
"""

from __future__ import annotations

from netforge.security.banner import BannerGrabOperation, grab_banner
from netforge.security.headers import (
    SECURITY_HEADERS,
    HttpHeaderAnalysisOperation,
    analyze_headers,
)
from netforge.security.scanner import PortScannerOperation, PortScanRequest, PortScanResponse
from netforge.security.tls import TlsInspectionOperation, inspect_tls

__all__ = [
    "BannerGrabOperation",
    "HttpHeaderAnalysisOperation",
    "PortScanRequest",
    "PortScanResponse",
    "PortScannerOperation",
    "SECURITY_HEADERS",
    "TlsInspectionOperation",
    "analyze_headers",
    "grab_banner",
    "inspect_tls",
]
