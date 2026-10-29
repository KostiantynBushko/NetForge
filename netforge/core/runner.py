"""Running external commands.

Several capabilities -- ping, traceroute, ``tc``, ``tcpdump`` -- are
implemented by calling a system tool.  They all do it through
:class:`CommandRunner`, and the runner is injectable, so a test can drive
those capabilities without the tool being installed and without the test
touching the network.

That injection point is the reason this module exists as a separate
abstraction rather than a helper function: the alternative is a capability
that can only be tested on a machine that happens to have the binary.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence

from netforge.core.exceptions import ConfigurationError
from netforge.core.logging import get_logger

__all__ = ["CommandResult", "CommandRunner", "SubprocessCommandRunner", "which"]

_logger = get_logger("core.runner")


@dataclass(slots=True)
class CommandResult:
    """The outcome of running an external command."""

    argv: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    env: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Return ``True`` when the command exited with status zero."""
        return self.returncode == 0

    @property
    def command(self) -> str:
        """Return the command as a copy-pasteable shell string."""
        return " ".join(_quote(part) for part in self.argv)

    def check(self) -> "CommandResult":
        """Raise :class:`RuntimeError` when the command failed."""
        if not self.ok:
            detail = (self.stderr or self.stdout).strip()
            raise RuntimeError(f"command failed ({self.returncode}): {self.command}\n{detail}".rstrip())
        return self


class CommandRunner(Protocol):
    """The interface a command runner must provide."""

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
        stdin: bytes | None = None,
    ) -> CommandResult:
        """Run ``argv`` and return its result."""
        ...


class SubprocessCommandRunner:
    """A :class:`CommandRunner` that spawns real processes.

    The command is given as a list, never as a string, so there is no shell
    in the middle and no way for a host name to be interpreted as syntax.
    """

    def __init__(self, *, default_timeout: float | None = 30.0) -> None:
        self.default_timeout = default_timeout

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
        stdin: bytes | None = None,
    ) -> CommandResult:
        argv = [str(part) for part in argv]
        if not argv:
            raise ConfigurationError("cannot run an empty command")

        budget = self.default_timeout if timeout is None else timeout
        started = time.perf_counter()
        environ = dict(os.environ)
        if env:
            environ.update({str(k): str(v) for k, v in env.items()})

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=environ,
            )
        except FileNotFoundError as exc:
            raise ConfigurationError(
                f"{argv[0]!r} is not installed; it is required for this capability"
            ) from exc

        try:
            if budget is None:
                stdout, stderr = await process.communicate(stdin)
            else:
                stdout, stderr = await asyncio.wait_for(process.communicate(stdin), timeout=budget)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise

        return CommandResult(
            argv=argv,
            returncode=process.returncode or 0,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            duration_ms=(time.perf_counter() - started) * 1000.0,
            env={str(k): str(v) for k, v in (env or {}).items()},
        )


def which(program: str) -> str | None:
    """Return the full path of ``program``, or ``None`` when it is absent."""
    return shutil.which(program)


def _quote(part: str) -> str:
    if part and all(ch.isalnum() or ch in "-_./:=@," for ch in part):
        return part
    return "'" + part.replace("'", "'\"'\"'") + "'"
