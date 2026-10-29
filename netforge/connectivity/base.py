"""The base of every connection.

A connection has a lifecycle -- open, use, close -- and it can be used as
an async context manager, which is how it is meant to be used:

.. code-block:: python

    async with TcpConnection("10.0.0.1", 22) as connection:
        await connection.write(b"hello")

Using it as a context manager is not a convenience: it guarantees the
connection is closed even when the body raises, and a leaked TCP connection
on a router is a resource leak on somebody else's machine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from netforge.core.logging import get_logger

__all__ = ["Connection", "ConnectionResult", "ConnectionState"]

_logger = get_logger("connectivity.base")


class ConnectionState(StrEnum):
    """The lifecycle state of a connection."""

    NEW = "new"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    CLOSED = "closed"
    FAILED = "failed"


@dataclass(slots=True)
class ConnectionResult:
    """The outcome of a command or transfer over a connection."""

    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.ok


class Connection(ABC):
    """Base class of every NetForge connection."""

    def __init__(self, *, timeout: float | None = 30.0) -> None:
        self.timeout = timeout
        self.state: ConnectionState = ConnectionState.NEW
        self.last_error: str | None = None

    @property
    def is_connected(self) -> bool:
        """Return ``True`` when the connection is usable."""
        return self.state is ConnectionState.CONNECTED

    @abstractmethod
    async def connect(self) -> None:
        """Open the connection."""

    @abstractmethod
    async def close(self) -> None:
        """Close the connection.  Must be safe to call more than once."""

    async def __aenter__(self) -> "Connection":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    def _mark_failed(self, error: BaseException | str) -> None:
        self.state = ConnectionState.FAILED
        self.last_error = str(error)
        _logger.warning("%s failed: %s", type(self).__name__, self.last_error)
