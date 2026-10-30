"""Traffic manipulation.

Controlled modification of traffic: a proxy that sits in the path and
forwards what it receives.
"""

from __future__ import annotations

from netforge.manipulation.proxy import (
    ProxyOperation,
    ProxyRequest,
    ProxyResponse,
    ProxyStats,
    TcpProxy,
    run_tcp_proxy,
)

__all__ = [
    "ProxyOperation",
    "ProxyRequest",
    "ProxyResponse",
    "ProxyStats",
    "TcpProxy",
    "run_tcp_proxy",
]
