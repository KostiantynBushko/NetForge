"""Network emulation.

Simulating the network a device is on: the latency, the jitter, the loss
and the bandwidth.  The profiles are pure data; applying them changes the
machine's own network, which is why the operation that does it is declared
at the system modification level.
"""

from __future__ import annotations

from netforge.emulation.netem import (
    NetEmController,
    NetEmOperation,
    build_netem_command,
    parse_qdisc,
)
from netforge.emulation.profile import (
    PROFILE_PRESETS,
    NetworkProfile,
    ProfileOperation,
    grade_profile,
)

__all__ = [
    "NetEmController",
    "NetEmOperation",
    "NetworkProfile",
    "PROFILE_PRESETS",
    "ProfileOperation",
    "build_netem_command",
    "grade_profile",
    "parse_qdisc",
]
