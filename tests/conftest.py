"""Shared fixtures for the NetForge test suite."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import pytest

from netforge.core.bootstrap import load_builtin_operations
from netforge.core.context import ExecutionContext
from netforge.core.runner import CommandResult
from netforge.registry.registry import OperationRegistry


@dataclass
class FakeRunner:
    """A command runner that answers from a script instead of running anything.

    The capabilities that shell out -- ping, traceroute, ``tc`` -- are
    driven through this in the tests, so the suite needs neither the system
    tools nor the network.
    """

    responses: dict[str, CommandResult] = field(default_factory=dict)
    default: CommandResult | None = None
    calls: list[list[str]] = field(default_factory=list)

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
        stdin: bytes | None = None,
    ) -> CommandResult:
        """Return the scripted answer for ``argv``."""
        command = [str(part) for part in argv]
        self.calls.append(command)
        key = " ".join(command)
        for scripted, result in self.responses.items():
            if key.startswith(scripted):
                return result
        if self.default is not None:
            return self.default
        return CommandResult(argv=command, returncode=127, stderr="command not found")


def result(stdout: str = "", *, returncode: int = 0, stderr: str = "") -> CommandResult:
    """Build a :class:`CommandResult` for a scripted answer."""
    return CommandResult(argv=["fake"], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def registry() -> OperationRegistry:
    """Return a registry holding every built-in operation."""
    return load_builtin_operations()


@pytest.fixture
def fake_runner() -> FakeRunner:
    """Return a command runner that answers from a script."""
    return FakeRunner()


@pytest.fixture
def context() -> ExecutionContext:
    """Return a default execution context."""
    return ExecutionContext()


@pytest.fixture
def anyio_backend() -> str:
    """Keep anyio on asyncio."""
    return "asyncio"


def unused(*args: Any) -> None:
    """Do nothing; used to keep optional imports referenced."""
    return None
