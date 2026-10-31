"""Shared fixtures for the NetForge test suite."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _bind_root_package() -> None:
    """Bind the import name ``netforge`` to the project root.

    The project root *is* the package: the capability packages live at the
    top of the repository and ``pyproject.toml`` maps them back under the
    ``netforge`` name when the distribution is built.  The checkout on disk
    is called ``NetForge`` while the importable name is ``netforge``, so
    bind that name explicitly here.

    This lets the suite run straight from a checkout, with no install
    step, and it is a no-op once the distribution is installed.
    """
    if "netforge" in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        "netforge",
        _ROOT / "__init__.py",
        submodule_search_locations=[str(_ROOT)],
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules["netforge"] = module
    spec.loader.exec_module(module)


_bind_root_package()

from netforge.core.bootstrap import load_builtin_operations  # noqa: E402
from netforge.core.context import ExecutionContext  # noqa: E402
from netforge.core.runner import CommandResult  # noqa: E402
from netforge.registry.registry import OperationRegistry  # noqa: E402


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
