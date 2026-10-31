"""The connectivity layer.

Connectivity is how NetForge reaches remote systems: SSH, HTTP, WebSocket,
TCP and UDP.  Each of them is a *connection* -- a reusable object with a
lifecycle -- and, where it makes sense, an *operation* that exposes the
capability to adapters.

The connections are written against :mod:`asyncio` and the standard
library.  ``asyncssh`` is the single exception and is an optional extra:
the SSH connection imports it lazily and reports a clear error when it is
missing, so the rest of the framework works on a machine without it.
"""

from __future__ import annotations

from netforge.connectivity.base import Connection, ConnectionResult, ConnectionState
from netforge.connectivity.http import HttpConnection, HttpRequestOperation
from netforge.connectivity.tcp import TcpConnection, TcpConnectOperation
from netforge.connectivity.udp import UdpConnection, UdpProbeOperation
from netforge.connectivity.websocket import WebSocketConnection

__all__ = [
    "Connection",
    "ConnectionResult",
    "ConnectionState",
    "HttpConnection",
    "HttpRequestOperation",
    "TcpConnectOperation",
    "TcpConnection",
    "UdpConnection",
    "UdpProbeOperation",
    "WebSocketConnection",
]
