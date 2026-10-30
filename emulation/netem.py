"""Applying network conditions with ``tc``.

``tc`` -- the traffic control tool of Linux -- is what actually applies a
profile to an interface.  The class here builds the command line, runs it
through the framework's command runner, and parses what ``tc qdisc show``
reports.

Because it changes the network of the machine it runs on, the operation is
declared at the **system modification** level -- the highest one.

The class does not require ``tc`` to be installed to be *constructed* or
*tested*: the command line is built by a pure function, and the runner is
injected.  That is what makes it testable.
"""

from __future__ import annotations

import time

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.emulation.profile import PROFILE_PRESETS, NetworkProfile
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["NetEmController", "NetEmOperation", "build_netem_command", "parse_qdisc"]

_logger = get_logger("emulation.netem")


def build_netem_command(
    interface: str,
    profile: NetworkProfile,
    *,
    root: bool = True,
) -> list[str]:
    """Build the ``tc`` command line that applies ``profile``.

    The delay is expressed with the correlation and the distribution that
    ``netem`` understands, so the jitter is real jitter and not a constant
    offset.
    """
    argv = ["tc", "qdisc", "replace", "dev", interface, "root", "netem"]
    argv.append(f"delay {profile.latency_ms:.3f}ms")
    if profile.jitter_ms > 0:
        argv[-1] += f" {profile.jitter_ms:.3f}ms"
    if profile.loss_percent > 0:
        argv.append(f"loss {profile.loss_percent:.3f}%")
    if profile.bandwidth_mbps:
        argv.extend(["rate", f"{profile.bandwidth_mbps:.3f}mbit"])
    return argv


def parse_qdisc(text: str) -> list[dict[str, str]]:
    """Parse the output of ``tc qdisc show``.

    A line looks like this::

        qdisc netem 8001: root refcnt 2 limit 1000 delay 100ms

    and becomes ``{"kind": "netem", "handle": "8001", "options": "root refcnt 2 ..."}``.
    """
    entries: list[dict[str, str]] = []
    for line in (text or "").splitlines():
        tokens = line.strip().split()
        if not tokens:
            continue
        entry: dict[str, str] = {}
        if tokens[0] == "qdisc" and len(tokens) >= 2:
            entry["kind"] = tokens[1]
            if len(tokens) >= 3:
                entry["handle"] = tokens[2].rstrip(":")
            entry["options"] = " ".join(tokens[3:])
        else:
            entry["kind"] = tokens[0]
            entry["options"] = " ".join(tokens[1:])
        entries.append(entry)
    return entries


class NetEmController:
    """Applies and removes network conditions on an interface."""

    def __init__(self, interface: str) -> None:
        self.interface = interface

    async def apply(self, profile: NetworkProfile, context: ExecutionContext) -> str:
        """Apply the profile and return the output of ``tc``."""
        argv = build_netem_command(self.interface, profile)
        result = await context.runner().run(argv, timeout=context.timeout)
        if not result.ok:
            raise RuntimeError(
                f"tc failed with the status {result.returncode}: "
                f"{(result.stderr or result.stdout).strip()}"
            )
        return result.stdout

    async def reset(self, context: ExecutionContext) -> str:
        """Remove the conditions from the interface."""
        argv = ["tc", "qdisc", "del", "dev", self.interface, "root"]
        result = await context.runner().run(argv, timeout=context.timeout)
        # Deleting a queue discipline that is not there is not an error.
        if not result.ok and "no such" not in (result.stderr or "").lower():
            raise RuntimeError(
                f"tc failed with the status {result.returncode}: "
                f"{(result.stderr or result.stdout).strip()}"
            )
        return result.stdout

    async def show(self, context: ExecutionContext) -> list[dict[str, str]]:
        """Report the queue disciplines of the interface."""
        argv = ["tc", "qdisc", "show", "dev", self.interface]
        result = await context.runner().run(argv, timeout=context.timeout)
        return parse_qdisc(result.stdout)


class NetEmRequest(RequestModel):
    """Request of :class:`NetEmOperation`."""

    interface: str = Field(min_length=1, description="The interface to configure.")
    profile: str | None = Field(default=None, description="The name of a preset profile.")
    latency_ms: float | None = Field(default=None, ge=0.0, description="A custom latency.")
    jitter_ms: float | None = Field(default=None, ge=0.0, description="A custom jitter.")
    loss_percent: float | None = Field(default=None, ge=0.0, le=100.0, description="A custom loss.")
    bandwidth_mbps: float | None = Field(default=None, gt=0.0, description="A custom bandwidth.")
    action: str = Field(default="apply", description="'apply', 'reset' or 'show'.")
    dry_run: bool = Field(default=False, description="Report the command without running it.")


class NetEmResponse(ResponseModel):
    """Response of :class:`NetEmOperation`."""

    interface: str = Field(description="The interface the conditions were applied to.")
    action: str = Field(description="What was done: applied, reset or shown.")
    command: list[str] = Field(default_factory=list, description="The command that was run.")
    applied: bool = Field(default=False, description="Whether the conditions were applied.")
    qdisc: list[dict[str, str]] = Field(default_factory=list, description="The queueing discipline that is in place.")
    profile: dict[str, object] = Field(default_factory=dict, description="The profile that was applied.")


class NetEmOperation(Operation[NetEmRequest, NetEmResponse]):
    """Apply, reset or show the network conditions of an interface."""

    name = "emulation.netem"
    category = CapabilityCategory.EMULATION
    risk_level = RiskLevel.SYSTEM_MODIFICATION
    summary = "Apply, reset or show the network conditions of an interface."
    description = (
        "Applies a network profile to an interface with the Linux traffic control "
        "tool, resets it, or reports what is currently applied. This changes the "
        "network of the machine it runs on, which is why the operation is declared at "
        "the system modification level."
    )
    tags = frozenset({"emulation", "netem", "tc", "network", "latency"})
    requires_privilege = True

    request_model = NetEmRequest
    response_model = NetEmResponse

    async def execute(self, request: NetEmRequest, context: ExecutionContext) -> NetEmResponse:
        """Apply, reset or show."""
        started = time.perf_counter()
        controller = NetEmController(request.interface)
        action = request.action.lower()

        if action == "show":
            qdisc = await controller.show(context)
            return NetEmResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                interface=request.interface,
                action=action,
                qdisc=qdisc,
            )

        if action == "reset":
            if request.dry_run or context.dry_run:
                return NetEmResponse(
                    operation=self.name,
                    risk_level=self.risk_level.label,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    interface=request.interface,
                    action=action,
                    command=["tc", "qdisc", "del", "dev", request.interface, "root"],
                    applied=False,
                )
            await controller.reset(context)
            return NetEmResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                interface=request.interface,
                action=action,
                command=["tc", "qdisc", "del", "dev", request.interface, "root"],
                applied=True,
            )

        if request.profile:
            profile = PROFILE_PRESETS.get(request.profile.lower())
            if profile is None:
                return NetEmResponse(
                    operation=self.name,
                    risk_level=self.risk_level.label,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    interface=request.interface,
                    action=action,
                    warnings=[
                        f"there is no preset named {request.profile!r}; "
                        f"the presets are: {', '.join(sorted(PROFILE_PRESETS))}"
                    ],
                )
        else:
            profile = NetworkProfile(
                name="custom",
                latency_ms=request.latency_ms or 0.0,
                jitter_ms=request.jitter_ms or 0.0,
                loss_percent=request.loss_percent or 0.0,
                bandwidth_mbps=request.bandwidth_mbps,
                description="A custom profile.",
            )

        command = build_netem_command(request.interface, profile)
        if request.dry_run or context.dry_run:
            return NetEmResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                interface=request.interface,
                action=action,
                command=command,
                applied=False,
                profile=profile.to_dict(),
            )

        try:
            await controller.apply(profile, context)
        except RuntimeError as exc:
            return NetEmResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                interface=request.interface,
                action=action,
                command=command,
                applied=False,
                profile=profile.to_dict(),
                warnings=[str(exc)],
            )

        return NetEmResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            interface=request.interface,
            action=action,
            command=command,
            applied=True,
            profile=profile.to_dict(),
        )
