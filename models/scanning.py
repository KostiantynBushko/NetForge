"""How hard a scan pushes, and how visible it is.

A scan is loud.  Every probe is a packet that the target, or the
equipment in front of it, can see, and a scan that comes in a hurry is
easy to tell from the traffic around it.  The **aggressiveness** of a
scan is the trade-off between how fast it runs and how much of a trace it
leaves behind.

The levels are the ones nmap uses for its timing templates, so that the
two agree:

``paranoid``
    one probe at a time, a second between them, and a long patience.
    The slowest, and the quietest.

``stealth``
    one probe at a time and half a second between them, and -- when the
    scan is run with nmap and the process is root -- a scan that never
    completes the handshake.

``polite``
    a few probes at a time, and a tenth of a second between them.

``normal``
    the default: as fast as the operation was before the levels existed.

``aggressive``
    as many probes at once as the target will take, and no waiting.

The level is a **profile**: it says how many probes run at once, how
patient each one is, and how long the scan waits between them.  A
profile that leaves something out means *the operation keeps its own
default* -- so the normal level changes nothing at all.

The profile is about pacing.  What is on the wire is the business of the
engine that runs the scan: the native one opens a connection per port,
which the target sees, and nmap can be asked for a half-open scan, which
it cannot.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "Aggressiveness",
    "ScanEngine",
    "ScanProfile",
    "PROFILES",
    "the_profile",
]


class ScanEngine(StrEnum):
    """The implementation that runs a scan.

    ``native``
        the implementation of NetForge itself: standard library, no
        external tool, and nothing to install.

    ``nmap``
        nmap, when it is installed.  It knows more about the services
        behind the open ports, and it can be asked to be quieter.
    """

    NATIVE = "native"
    NMAP = "nmap"

    @property
    def label(self) -> str:
        """The human-readable name of the engine."""
        return "nmap" if self is ScanEngine.NMAP else "the native scanner"

    @property
    def description(self) -> str:
        """A one-line description of what the engine does."""
        return _ENGINE_DESCRIPTIONS[self]

    @classmethod
    def parse(cls, value: str | ScanEngine) -> ScanEngine:
        """Coerce ``value`` into a :class:`ScanEngine`."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError(f"cannot interpret {value!r} as a scan engine")
        text = value.strip().lower()
        try:
            return cls(text)
        except ValueError as exc:
            raise ValueError(f"unknown scan engine: {value!r}") from exc


class Aggressiveness(StrEnum):
    """The level of a scan."""

    PARANOID = "paranoid"
    STEALTH = "stealth"
    POLITE = "polite"
    NORMAL = "normal"
    AGGRESSIVE = "aggressive"

    @property
    def label(self) -> str:
        """The human-readable name of the level."""
        return self.name.title()

    @property
    def description(self) -> str:
        """A one-line description of what the level does."""
        return _DESCRIPTIONS[self]

    @classmethod
    def parse(cls, value: str | Aggressiveness) -> Aggressiveness:
        """Coerce ``value`` into an :class:`Aggressiveness`."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError(f"cannot interpret {value!r} as an aggressiveness")
        text = value.strip().lower().replace("-", "_").replace(" ", "_")
        try:
            return cls(text)
        except ValueError as exc:
            raise ValueError(f"unknown aggressiveness: {value!r}") from exc


@dataclass(frozen=True, slots=True)
class ScanProfile:
    """How a scan of a given level behaves.

    A value of ``None`` means the operation keeps its own default.
    """

    concurrency: int | None = None
    timeout: float | None = None
    delay: float = 0.0

    def the_concurrency(self, default: int) -> int:
        """The number of probes at once."""
        return default if self.concurrency is None else self.concurrency

    def the_timeout(self, default: float) -> float:
        """How patient one probe is, in seconds."""
        return default if self.timeout is None else self.timeout


#: The profile of every level.
PROFILES: dict[Aggressiveness, ScanProfile] = {
    Aggressiveness.PARANOID: ScanProfile(concurrency=1, timeout=10.0, delay=1.0),
    Aggressiveness.STEALTH: ScanProfile(concurrency=1, timeout=5.0, delay=0.5),
    Aggressiveness.POLITE: ScanProfile(concurrency=8, delay=0.1),
    Aggressiveness.NORMAL: ScanProfile(),
    Aggressiveness.AGGRESSIVE: ScanProfile(concurrency=128, timeout=1.0),
}

_DESCRIPTIONS: dict[Aggressiveness, str] = {
    Aggressiveness.PARANOID: "One probe at a time, a second between them, and a long patience.",
    Aggressiveness.STEALTH: "One probe at a time, half a second between them, and no handshake when nmap and root allow it.",
    Aggressiveness.POLITE: "A few probes at a time, and a tenth of a second between them.",
    Aggressiveness.NORMAL: "The default: the speed the operation had before the levels existed.",
    Aggressiveness.AGGRESSIVE: "As many probes at once as the target will take, and no waiting.",
}


_ENGINE_DESCRIPTIONS: dict[ScanEngine, str] = {
    ScanEngine.NATIVE: "The scanner of NetForge itself, on the standard library alone.",
    ScanEngine.NMAP: "nmap, when it is installed: it names the product and the version behind a port.",
}


def the_profile(aggressiveness: str | Aggressiveness) -> ScanProfile:
    """The profile of a level."""
    return PROFILES[Aggressiveness.parse(aggressiveness)]
