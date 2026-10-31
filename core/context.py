"""The execution context.

The context is the object every operation receives alongside its request.
It carries the three things an operation cannot decide for itself:

* **the configuration** -- timeouts, TLS policy, the user agent;
* **the risk ceiling** -- the highest risk level this caller may run at;
* **the credentials** -- named secrets, resolved lazily.

The risk ceiling is enforced *by the framework*, not by the operation.  An
operation that forgets to check it still cannot exceed it, because
:meth:`ExecutionContext.check_risk` is called before ``execute()`` is
entered.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from netforge.core.config import NetForgeConfig
from netforge.core.exceptions import RiskPolicyError
from netforge.core.runner import CommandRunner, SubprocessCommandRunner
from netforge.models.risk import RiskLevel

__all__ = ["Credential", "ExecutionContext"]


@dataclass(frozen=True, slots=True)
class Credential:
    """A named secret.

    ``secret`` may be ``None`` when the credential is only a *reference* --
    a key name that the underlying protocol resolves itself, such as an
    SSH agent or a cloud metadata service.  Operations that need the value
    itself must check :attr:`has_value`.
    """

    name: str
    username: str | None = None
    secret: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    @property
    def has_value(self) -> bool:
        """Return ``True`` when the secret value itself is available."""
        return self.secret is not None


@dataclass
class ExecutionContext:
    """Everything an operation needs from its caller."""

    config: NetForgeConfig = field(default_factory=NetForgeConfig)
    max_risk: RiskLevel = field(default=RiskLevel.SYSTEM_MODIFICATION)
    credentials: dict[str, Credential] = field(default_factory=dict)
    timeout: float | None = None
    dry_run: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    command_runner: CommandRunner | None = None

    def __post_init__(self) -> None:
        if self.timeout is None:
            self.timeout = self.config.default_timeout
        # The ceiling can never be above what the configuration allows.
        if self.max_risk > self.config.max_risk:
            self.max_risk = self.config.max_risk

    def runner(self) -> CommandRunner:
        """Return the command runner to use.

        A caller that has its own runner -- a test, a sandbox, an operator
        with a restricted PATH -- puts it on the context; otherwise a
        subprocess runner is created.
        """
        if self.command_runner is None:
            self.command_runner = SubprocessCommandRunner(default_timeout=self.timeout)
        return self.command_runner

    # -- risk ---------------------------------------------------------------

    def check_risk(self, operation: str, risk_level: RiskLevel) -> None:
        """Raise :class:`RiskPolicyError` when ``risk_level`` exceeds the ceiling."""
        if risk_level > self.max_risk:
            raise RiskPolicyError(operation, risk_level, self.max_risk)

    def permits(self, risk_level: RiskLevel) -> bool:
        """Return ``True`` when ``risk_level`` is within the ceiling."""
        return risk_level <= self.max_risk

    # -- credentials --------------------------------------------------------

    def credential(self, name: str) -> Credential:
        """Return the named credential, or an empty one when it is absent.

        Operations that require a credential should not raise on a missing
        one by themselves: a capability may be able to fall back to a
        key-based or agent-based authentication.  The operation decides.
        """
        return self.credentials.get(name, Credential(name=name))

    def has_credential(self, name: str) -> bool:
        """Return ``True`` when a credential with that name was supplied."""
        return name in self.credentials

    # -- time ---------------------------------------------------------------

    @asynccontextmanager
    async def deadline(self, timeout: float | None = None) -> AsyncIterator[None]:
        """Apply a time budget to the block.

        A timeout of ``None`` means "no budget", which is different from a
        budget of zero.
        """
        budget = self.timeout if timeout is None else timeout
        if budget is None:
            yield
            return
        async with asyncio.timeout(budget):
            yield
