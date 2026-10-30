"""Network condition profiles.

A profile describes the network a device *thinks* it is on: the latency,
the jitter, the loss, the bandwidth.  The profiles are pure data, and the
presets -- bad WiFi, cellular, satellite, a constrained IoT link -- are the
four cases the specification names.

The analysis of a profile is also pure: :func:`grade_profile` says whether
a profile is internally consistent and how severe it is, which is what an
agent needs before it applies one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = [
    "NetworkProfile",
    "PROFILE_PRESETS",
    "ProfileOperation",
    "grade_profile",
]

_logger = get_logger("emulation.profile")


@dataclass(frozen=True, slots=True)
class NetworkProfile:
    """A description of the network conditions to simulate."""

    name: str
    latency_ms: float = 0.0
    jitter_ms: float = 0.0
    loss_percent: float = 0.0
    bandwidth_mbps: float | None = None
    description: str = ""

    def validate(self) -> list[str]:
        """Return the problems with the profile; an empty list means it is valid."""
        problems: list[str] = []
        if self.latency_ms < 0:
            problems.append("the latency cannot be negative.")
        if self.jitter_ms < 0:
            problems.append("the jitter cannot be negative.")
        if not 0.0 <= self.loss_percent <= 100.0:
            problems.append("the loss must be between 0 and 100 percent.")
        if self.bandwidth_mbps is not None and self.bandwidth_mbps <= 0:
            problems.append("the bandwidth must be positive.")
        if self.jitter_ms > self.latency_ms and self.latency_ms > 0:
            problems.append(
                "the jitter is larger than the latency, which is not a condition any "
                "network can be in."
            )
        return problems

    @property
    def severity(self) -> str:
        """Return a one-word description of how severe the conditions are."""
        if self.loss_percent >= 10 or self.latency_ms >= 500:
            return "severe"
        if self.loss_percent >= 1 or self.latency_ms >= 150:
            return "moderate"
        return "mild"

    def to_dict(self) -> dict[str, object]:
        """Return the profile as a plain dictionary."""
        return {
            "name": self.name,
            "latency_ms": self.latency_ms,
            "jitter_ms": self.jitter_ms,
            "loss_percent": self.loss_percent,
            "bandwidth_mbps": self.bandwidth_mbps,
            "description": self.description,
            "severity": self.severity,
        }


#: The presets named in the specification.
PROFILE_PRESETS: dict[str, NetworkProfile] = {
    "bad_wifi": NetworkProfile(
        name="bad_wifi",
        latency_ms=120.0,
        jitter_ms=80.0,
        loss_percent=3.0,
        bandwidth_mbps=8.0,
        description="A congested wireless link: high jitter and a fair amount of loss.",
    ),
    "cellular": NetworkProfile(
        name="cellular",
        latency_ms=60.0,
        jitter_ms=30.0,
        loss_percent=0.5,
        bandwidth_mbps=25.0,
        description="A mobile network: moderate latency and variable throughput.",
    ),
    "satellite": NetworkProfile(
        name="satellite",
        latency_ms=650.0,
        jitter_ms=40.0,
        loss_percent=0.2,
        bandwidth_mbps=100.0,
        description="A geostationary satellite link: very high latency, good throughput.",
    ),
    "constrained_iot": NetworkProfile(
        name="constrained_iot",
        latency_ms=900.0,
        jitter_ms=200.0,
        loss_percent=5.0,
        bandwidth_mbps=0.1,
        description="A constrained IoT link: very slow, lossy and unreliable.",
    ),
    "clean": NetworkProfile(
        name="clean",
        latency_ms=1.0,
        jitter_ms=0.2,
        loss_percent=0.0,
        bandwidth_mbps=1000.0,
        description="An ideal link, used as a control when testing.",
    ),
}


def grade_profile(profile: NetworkProfile) -> list[str]:
    """Return the problems with a profile."""
    return profile.validate()


class ProfileRequest(RequestModel):
    """Request of :class:`ProfileOperation`."""

    name: str | None = Field(default=None, description="The name of a preset profile.")
    latency_ms: float | None = Field(default=None, ge=0.0, description="The latency to simulate.")
    jitter_ms: float | None = Field(default=None, ge=0.0, description="The jitter to simulate.")
    loss_percent: float | None = Field(default=None, ge=0.0, le=100.0, description="The packet loss.")
    bandwidth_mbps: float | None = Field(default=None, gt=0.0, description="The bandwidth limit.")


class ProfileResponse(ResponseModel):
    """Response of :class:`ProfileOperation`."""

    profile: dict[str, object] = Field(default_factory=dict, description="The profile that was described.")
    presets: list[str] = Field(default_factory=list, description="The built-in presets.")
    problems: list[str] = Field(default_factory=list, description="The problems the profile carries.")


class ProfileOperation(Operation[ProfileRequest, ProfileResponse]):
    """Describe a network profile, or list the presets."""

    name = "emulation.profile"
    category = CapabilityCategory.EMULATION
    risk_level = RiskLevel.SAFE
    summary = "Describe a network profile or list the built-in presets."
    description = (
        "Returns the network conditions of a preset -- bad WiFi, cellular, satellite, a "
        "constrained IoT link -- or describes a custom one. Nothing is applied to the "
        "network by this operation, so it is declared at the safe level."
    )
    tags = frozenset({"emulation", "profile", "network", "conditions"})

    request_model = ProfileRequest
    response_model = ProfileResponse

    async def execute(self, request: ProfileRequest, context: ExecutionContext) -> ProfileResponse:
        """Describe the profile."""
        started = time.perf_counter()

        if request.name:
            preset = PROFILE_PRESETS.get(request.name.lower())
            if preset is None:
                return ProfileResponse(
                    operation=self.name,
                    risk_level=self.risk_level.label,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    profile={},
                    presets=sorted(PROFILE_PRESETS),
                    problems=[
                        f"there is no preset named {request.name!r}; "
                        f"the presets are: {', '.join(sorted(PROFILE_PRESETS))}"
                    ],
                )
            profile = preset
        else:
            profile = NetworkProfile(
                name="custom",
                latency_ms=request.latency_ms or 0.0,
                jitter_ms=request.jitter_ms or 0.0,
                loss_percent=request.loss_percent or 0.0,
                bandwidth_mbps=request.bandwidth_mbps,
                description="A custom profile.",
            )

        return ProfileResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            profile=profile.to_dict(),
            presets=sorted(PROFILE_PRESETS),
            problems=grade_profile(profile),
        )
