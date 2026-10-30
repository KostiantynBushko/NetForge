"""The base of every protocol client.

A protocol client is a small state machine over a socket: it opens a
session, it exchanges messages, it closes.  :class:`ProtocolAdapter`
gives them a common shape so the framework -- and a test -- can treat them
alike.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from netforge.core.exceptions import NetForgeError
from netforge.core.logging import get_logger

__all__ = ["ProtocolAdapter", "ProtocolError", "ProtocolResponse"]

_logger = get_logger("protocols.base")


class ProtocolError(NetForgeError):
    """A protocol exchange failed."""


@dataclass(slots=True)
class ProtocolResponse:
    """A decoded protocol message."""

    payload: bytes
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Return the payload decoded as UTF-8."""
        return self.payload.decode("utf-8", errors="replace")


class ProtocolAdapter(ABC):
    """Base class of every protocol client."""

    #: The wire protocol this client speaks.
    protocol: str = "generic"

    #: The default port of the protocol.
    default_port: int = 0

    def __init__(self, host: str, port: int | None = None, *, timeout: float | None = 30.0) -> None:
        self.host = host
        self.port = port if port is not None else self.default_port
        self.timeout = timeout
        self.connected = False

    @abstractmethod
    async def connect(self) -> None:
        """Open the session."""

    @abstractmethod
    async def close(self) -> None:
        """Close the session."""

    @abstractmethod
    async def exchange(self, payload: bytes) -> ProtocolResponse:
        """Send ``payload`` and return the decoded reply."""

    async def __aenter__(self) -> "ProtocolAdapter":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    def describe(self) -> dict[str, Any]:
        """Return a description of the client."""
        return {
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "connected": self.connected,
        }
