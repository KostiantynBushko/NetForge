"""The engine: what the sentinel watches, and how it keeps track of it.

A scan is not one event.  It is many small ones — a SYN here, a RST
there, ten ports in a second — and none of them means anything on its
own.  What makes it a scan is the *shape*: one address, many ports, in
a short time.

So the engine keeps a **window** of what it has seen, and the rules read
the window.  The unit is the **attempt**: one address trying to reach
one port.  An attempt is open when the handshake finished, reset when
the port was closed, and silent when neither side said anything.

The window is measured in the clock of the capture, not in the clock of
the machine: a file that is analysed today says the same thing as the
same file analysed tomorrow, and a monitor that is watching says the
same thing as the file it would have written.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import Field

from netforge.analysis.flow import Packet
from netforge.models.base import NetForgeModel
from netforge.sentinel.alerts import Alert

__all__ = ["Attempt", "Window", "Thresholds", "Rule", "Sentinel"]


class Thresholds(NetForgeModel):
    """How much activity a rule needs before it says anything."""

    distinct_ports: int = Field(
        default=10, ge=1, description="How many different ports make a sweep."
    )
    half_open: int = Field(
        default=5, ge=1, description="How many closed ports make a half-open scan."
    )
    silent_handshakes: int = Field(
        default=10, ge=1, description="How many empty connections make a scan."
    )
    service_probes: int = Field(
        default=3, ge=1, description="How many probed ports make a service probe."
    )


@dataclass(slots=True)
class Attempt:
    """One address trying to reach one port."""

    source: str
    destination: str
    source_port: int
    destination_port: int
    protocol: str = "tcp"
    started: float = 0.0
    completed: bool = False
    reset: bool = False
    payload_from_source: int = 0
    payload_from_target: int = 0
    packets: int = 0

    @property
    def key(self) -> tuple[str, int, str, int]:
        """The tuple that identifies the attempt."""
        return (self.source, self.source_port, self.destination, self.destination_port)

    @property
    def state(self) -> str:
        """Whether the port was open, closed, or never answered."""
        if self.reset:
            return "reset"
        if self.completed:
            return "open"
        return "pending"

    @property
    def silent(self) -> bool:
        """Whether nobody said anything on this connection."""
        return self.payload_from_source == 0 and self.payload_from_target == 0

    @property
    def probed(self) -> bool:
        """Whether the source spoke first, which is what a probe does."""
        return self.payload_from_source > 0 and self.payload_from_target == 0

    def to_dict(self) -> dict[str, Any]:
        """Return the attempt as a plain dictionary."""
        return {
            "source": self.source,
            "destination": self.destination,
            "source_port": self.source_port,
            "destination_port": self.destination_port,
            "state": self.state,
            "payload_from_source": self.payload_from_source,
            "payload_from_target": self.payload_from_target,
        }


@dataclass(slots=True)
class Window:
    """The attempts in the window, and what can be asked of them."""

    attempts: list[Attempt] = field(default_factory=list)
    latest: float = 0.0

    def grouped_by_source(self) -> dict[str, list[Attempt]]:
        """The attempts, grouped by the address that made them."""
        grouped: dict[str, list[Attempt]] = {}
        for attempt in self.attempts:
            grouped.setdefault(attempt.source, []).append(attempt)
        return grouped

    def the_ports_of(self, source: str, destination: str | None = None) -> set[int]:
        """The destination ports one address touched."""
        return {
            attempt.destination_port
            for attempt in self.attempts
            if attempt.source == source
            and (destination is None or attempt.destination == destination)
        }

    def the_destinations_of(self, source: str) -> set[str]:
        """The addresses one address touched."""
        return {
            attempt.destination
            for attempt in self.attempts
            if attempt.source == source
        }

    def of_state(self, source: str, state: str) -> list[Attempt]:
        """The attempts of one address that ended in a given state."""
        return [
            attempt
            for attempt in self.attempts
            if attempt.source == source and attempt.state == state
        ]


class Rule(Protocol):
    """A rule reads the window and says what it found."""

    name: str
    severity: str
    summary: str

    def evaluate(self, window: Window) -> list[Alert]:
        """Return the alerts the window holds."""
        ...


class Sentinel:
    """Watches the traffic and decides what is suspicious.

    The sentinel is fed packets and holds a window of the attempts it
    saw.  The rules are run over that window, and each alert is reported
    once: a sweep that lasts ten minutes is one finding, not six
    hundred.
    """

    def __init__(
        self,
        *,
        window_seconds: float = 60.0,
        rules: Iterable[Rule] | None = None,
        thresholds: Thresholds | None = None,
    ) -> None:
        self.window_seconds = window_seconds
        self.thresholds = thresholds or Thresholds()
        self.rules: list[Rule] = list(rules) if rules is not None else []
        self._attempts: dict[tuple[str, int, str, int], Attempt] = {}
        self._order: list[tuple[str, int, str, int]] = []
        self._reported: set[str] = set()
        self._latest: float = 0.0
        self._seen: int = 0

    @property
    def packets_seen(self) -> int:
        """How many packets the sentinel was fed."""
        return self._seen

    @property
    def attempts_seen(self) -> int:
        """How many attempts the sentinel holds."""
        return len(self._attempts)

    @property
    def the_attempts(self) -> list[Attempt]:
        """The attempts the sentinel holds."""
        return list(self._attempts.values())

    @property
    def latest_timestamp(self) -> float:
        """The timestamp of the newest packet."""
        return self._latest

    def feed(self, packet: Packet) -> None:
        """Take one packet."""
        self._seen += 1
        self._latest = max(self._latest, packet.timestamp)
        self._expire()

        if packet.protocol != "tcp":
            return
        if packet.source_port is None or packet.destination_port is None:
            return

        flags = set(packet.info.split(",")) if packet.info else set()

        if "SYN" in flags and "ACK" not in flags:
            # A connection starts here: the source is the one probing.
            key = (packet.source, packet.source_port, packet.destination, packet.destination_port)
            attempt = self._attempts.get(key)
            if attempt is None:
                attempt = Attempt(
                    source=packet.source,
                    destination=packet.destination,
                    source_port=packet.source_port,
                    destination_port=packet.destination_port,
                    protocol="tcp",
                    started=packet.timestamp,
                )
                self._attempts[key] = attempt
                self._order.append(key)
            attempt.packets += 1
            return

        # Everything else belongs to an attempt.  The attempt is keyed
        # by the direction of the probe, so a packet from the source has
        # the key of the attempt and a packet from the target has the
        # other one.
        forward = (packet.source, packet.source_port, packet.destination, packet.destination_port)
        reverse = (packet.destination, packet.destination_port, packet.source, packet.source_port)
        attempt = self._attempts.get(forward)
        if attempt is None:
            attempt = self._attempts.get(reverse)
        if attempt is None:
            return

        attempt.packets += 1
        if "RST" in flags:
            attempt.reset = True
        elif "ACK" in flags and "SYN" not in flags:
            attempt.completed = True
        if packet.payload_length:
            if packet.source == attempt.source:
                attempt.payload_from_source += packet.payload_length
            else:
                attempt.payload_from_target += packet.payload_length

    def evaluate(self) -> list[Alert]:
        """Run the rules over the window, and return the new alerts."""
        window = Window(attempts=list(self._attempts.values()), latest=self._latest)
        alerts: list[Alert] = []
        for rule in self.rules:
            for alert in rule.evaluate(window):
                fingerprint = self._the_fingerprint(alert)
                if fingerprint in self._reported:
                    continue
                self._reported.add(fingerprint)
                alerts.append(alert)
        return alerts

    def _the_fingerprint(self, alert: Alert) -> str:
        """The identity of an alert, so that it is only reported once."""
        bucket = int(self._latest // self.window_seconds) if self.window_seconds else 0
        return f"{alert.rule}|{alert.source}|{alert.destination}|{bucket}"

    def _expire(self) -> None:
        """Forget the attempts that have fallen out of the window."""
        cutoff = self._latest - self.window_seconds
        keep: list[tuple[str, int, str, int]] = []
        for key in self._order:
            attempt = self._attempts.get(key)
            if attempt is None:
                continue
            if attempt.started < cutoff:
                del self._attempts[key]
            else:
                keep.append(key)
        self._order = keep


def the_alert(
    rule: Rule,
    source: str,
    destination: str | None,
    timestamp: float,
    evidence: dict[str, Any],
) -> Alert:
    """Build an alert the way the rules build them."""
    return Alert(
        rule=rule.name,
        severity=rule.severity,
        summary=rule.summary,
        source=source,
        destination=destination,
        timestamp=timestamp,
        evidence=evidence,
    )


def now() -> float:
    """The current time, as a Unix timestamp."""
    return time.time()
