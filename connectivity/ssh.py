"""SSH connectivity.

SSH is the transport for the whole configuration capability: backing up a
device, restoring a configuration, running a command.

``asyncssh`` is an optional extra.  It is imported lazily, inside
:func:`_load_asyncssh`, so the module can be imported -- and the operation
can be *listed* -- on a machine that does not have it.  Running the
operation without the extra raises
:class:`~netforge.core.exceptions.DependencyMissingError`, which names the
extra to install.

The risk level of a remote command is **manipulation** (level 3): the
command may change the state of the remote system, and NetForge does not
know which command it was asked to run.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import Field

from netforge.connectivity.base import Connection, ConnectionState
from netforge.core.context import ExecutionContext
from netforge.core.exceptions import DependencyMissingError
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["SshConnection", "SshExecuteOperation"]

_logger = get_logger("connectivity.ssh")

SSH_EXTRA = "ssh"


def _load_asyncssh() -> Any:
    """Import ``asyncssh`` or raise a clear, actionable error."""
    try:
        import asyncssh
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise DependencyMissingError(
            "asyncssh",
            extra=SSH_EXTRA,
            feature="SSH connectivity",
        ) from exc
    return asyncssh


class SshConnection(Connection):
    """An SSH connection to a remote host."""

    def __init__(
        self,
        host: str,
        *,
        port: int = 22,
        username: str | None = None,
        password: str | None = None,
        client_keys: list[str] | None = None,
        known_hosts: str | None = None,
        timeout: float | None = 30.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client_keys = client_keys
        self.known_hosts = known_hosts
        self._connection: Any = None

    async def connect(self) -> None:
        """Open the SSH session."""
        if self.is_connected:
            return
        asyncssh = _load_asyncssh()
        self.state = ConnectionState.CONNECTING

        kwargs: dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "known_hosts": self.known_hosts,
        }
        if self.username:
            kwargs["username"] = self.username
        if self.password:
            kwargs["password"] = self.password
        if self.client_keys:
            kwargs["client_keys"] = self.client_keys

        try:
            self._connection = await asyncio.wait_for(
                asyncssh.connect(**kwargs), timeout=self.timeout
            )
        except Exception as exc:  # asyncssh raises a wide range of transport errors
            self._mark_failed(exc)
            raise
        self.state = ConnectionState.CONNECTED

    async def close(self) -> None:
        """Close the SSH session."""
        connection, self._connection = self._connection, None
        if connection is not None:
            connection.close()
            try:
                await connection.wait_closed()
            except Exception:  # pragma: no cover - best effort
                pass
        self.state = ConnectionState.CLOSED

    async def execute(self, command: str, *, timeout: float | None = None) -> tuple[int, str, str]:
        """Run ``command`` remotely and return ``(exit_code, stdout, stderr)``."""
        if self._connection is None:
            raise ConnectionError("the connection is not open")
        result = await self._connection.run(command, check=False, timeout=timeout)
        return (
            int(result.exit_status if result.exit_status is not None else 0),
            result.stdout or "",
            result.stderr or "",
        )


class SshExecuteRequest(RequestModel):
    """Request of :class:`SshExecuteOperation`."""

    host: str = Field(description="The remote host.")
    command: str = Field(min_length=1, description="The command to run.")
    port: int = Field(default=22, ge=1, le=65535, description="The SSH port.")
    username: str | None = Field(default=None, description="The user to log in as.")
    password: str | None = Field(default=None, description="The password, if one is needed.")
    client_keys: list[str] | None = Field(default=None, description="Paths of the client keys.")
    timeout: float | None = Field(default=30.0, gt=0.0, description="Timeout in seconds.")


class SshExecuteResponse(ResponseModel):
    """Response of :class:`SshExecuteOperation`."""

    host: str = Field(description="The host the command ran on.")
    command: str = Field(description="The command that was run.")
    exit_code: int = Field(description="The exit code of the command.")
    stdout: str = Field(default="", description="What the command wrote to the standard output.")
    stderr: str = Field(default="", description="What the command wrote to the standard error.")
    duration_ms: float = Field(default=0.0, description="How long the command took, in milliseconds.")


class SshExecuteOperation(Operation[SshExecuteRequest, SshExecuteResponse]):
    """Run a command on a remote host over SSH."""

    name = "connectivity.ssh.execute"
    category = CapabilityCategory.CONNECTIVITY
    risk_level = RiskLevel.MANIPULATION
    summary = "Run a shell command on a remote host over SSH."
    description = (
        "Runs a shell command on a remote host over SSH and returns its exit code and "
        "output. The command may change the state of the remote system, which is why the "
        "operation is declared at the manipulation level rather than at the safe level."
    )
    tags = frozenset({"ssh", "remote", "command"})

    request_model = SshExecuteRequest
    response_model = SshExecuteResponse

    async def execute(
        self, request: SshExecuteRequest, context: ExecutionContext
    ) -> SshExecuteResponse:
        """Run the command and return its output."""
        connection = SshConnection(
            request.host,
            port=request.port,
            username=request.username,
            password=request.password,
            client_keys=request.client_keys,
            timeout=request.timeout,
        )
        started = time.perf_counter()
        try:
            await connection.connect()
            exit_code, stdout, stderr = await connection.execute(request.command)
        finally:
            await connection.close()

        return SshExecuteResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            host=request.host,
            command=request.command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
        )
