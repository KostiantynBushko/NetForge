"""The rules: what the sentinel knows about a scan.

Each rule is a small, named piece of knowledge about what a scan looks
like on the wire.  They are plain classes over a :class:`Window`, so
each one can be read on its own, and each one can be tested on its own.

The four rules here are the ones that describe the traffic NetForge
itself produces -- by the native scanner or by nmap -- and the ones a
host firewall sees when someone runs one of them against it.

A rule that fires is a *suspicion*, not a proof.  A host that answers
ten ports in a second may be a scanner, or it may be a monitoring agent,
or it may be a misconfiguration.  The severity says how much to believe
it, and the evidence is there so that a person can.
"""

from __future__ import annotations

from typing import Any

from netforge.sentinel.alerts import Alert, Severity
from netforge.sentinel.engine import Rule, Thresholds, Window, the_alert

__all__ = [
    "PortSweepRule",
    "HalfOpenScanRule",
    "SilentConnectionRule",
    "ServiceProbeRule",
    "the_default_rules",
]


class PortSweepRule:
    """One address, many ports, in a short time.

    This is the shape of every port scan there is, whatever tool made
    it: the native scanner, nmap with a connect scan, nmap with a
    half-open scan.  Only the timing and the technique differ.
    """

    name = "port-sweep"
    severity = Severity.HIGH.value
    summary = "One address touched many ports of another in a short time."

    def __init__(self, thresholds: Thresholds | None = None) -> None:
        self.thresholds = thresholds or Thresholds()

    def evaluate(self, window: Window) -> list[Alert]:
        """Look for a source that touched many ports."""
        alerts: list[Alert] = []
        for source, attempts in window.grouped_by_source().items():
            by_destination: dict[str, set[int]] = {}
            for attempt in attempts:
                by_destination.setdefault(attempt.destination, set()).add(
                    attempt.destination_port
                )
            for destination, ports in by_destination.items():
                if len(ports) < self.thresholds.distinct_ports:
                    continue
                evidence: dict[str, Any] = {
                    "distinct_ports": len(ports),
                    "ports": sorted(ports),
                    "attempts": len(attempts),
                    "window_seconds": window_seconds(window),
                }
                alerts.append(
                    the_alert(self, source, destination, window.latest, evidence)
                )
        return alerts


class HalfOpenScanRule:
    """Many ports that answered with a reset.

    A half-open scan -- nmap's ``-sS`` -- never completes the handshake.
    The closed ports answer with a reset, and the open ones say nothing
    at all.  A burst of resets towards one address is the fingerprint.
    """

    name = "half-open-scan"
    severity = Severity.HIGH.value
    summary = "One address was refused on many ports without completing a handshake."

    def __init__(self, thresholds: Thresholds | None = None) -> None:
        self.thresholds = thresholds or Thresholds()

    def evaluate(self, window: Window) -> list[Alert]:
        """Look for a source that was refused on many ports."""
        alerts: list[Alert] = []
        for source, attempts in window.grouped_by_source().items():
            by_destination: dict[str, list[int]] = {}
            for attempt in attempts:
                if attempt.state == "reset":
                    by_destination.setdefault(attempt.destination, []).append(
                        attempt.destination_port
                    )
            for destination, ports in by_destination.items():
                if len(ports) < self.thresholds.half_open:
                    continue
                evidence: dict[str, Any] = {
                    "refused_ports": len(ports),
                    "ports": sorted(ports),
                    "window_seconds": window_seconds(window),
                }
                alerts.append(
                    the_alert(self, source, destination, window.latest, evidence)
                )
        return alerts


class SilentConnectionRule:
    """Many connections that said nothing at all.

    The native scanner opens a connection to every port and closes it
    again.  Nothing is said on any of them: the handshake, and then
    nothing.  Ten of those in a row is not a client, it is a scanner.
    """

    name = "silent-connections"
    severity = Severity.MEDIUM.value
    summary = "One address opened many connections and said nothing on any of them."

    def __init__(self, thresholds: Thresholds | None = None) -> None:
        self.thresholds = thresholds or Thresholds()

    def evaluate(self, window: Window) -> list[Alert]:
        """Look for a source that opened many empty connections."""
        alerts: list[Alert] = []
        for source, attempts in window.grouped_by_source().items():
            silent = [
                attempt
                for attempt in attempts
                if attempt.completed and attempt.silent
            ]
            if len(silent) < self.thresholds.silent_handshakes:
                continue
            destinations = sorted({attempt.destination for attempt in silent})
            evidence: dict[str, Any] = {
                "silent_connections": len(silent),
                "ports": sorted({attempt.destination_port for attempt in silent}),
                "destinations": destinations,
                "window_seconds": window_seconds(window),
            }
            alerts.append(
                the_alert(self, source, destinations[0] if destinations else None, window.latest, evidence)
            )
        return alerts


class ServiceProbeRule:
    """A payload where the service should have spoken first.

    nmap's ``-sV`` sends a probe to every open port and reads the
    answer.  The probe is the interesting part: on most services the
    *server* speaks first, so a client that talks before it is asked is
    the one doing the asking.
    """

    name = "service-probe"
    severity = Severity.MEDIUM.value
    summary = "One address sent a payload to many ports before the service answered."

    def __init__(self, thresholds: Thresholds | None = None) -> None:
        self.thresholds = thresholds or Thresholds()

    def evaluate(self, window: Window) -> list[Alert]:
        """Look for a source that spoke first on many ports."""
        alerts: list[Alert] = []
        for source, attempts in window.grouped_by_source().items():
            probed = [attempt for attempt in attempts if attempt.probed]
            if len(probed) < self.thresholds.service_probes:
                continue
            destinations = sorted({attempt.destination for attempt in probed})
            evidence: dict[str, Any] = {
                "probed_ports": len(probed),
                "ports": sorted({attempt.destination_port for attempt in probed}),
                "destinations": destinations,
                "bytes_sent": sum(attempt.payload_from_source for attempt in probed),
                "window_seconds": window_seconds(window),
            }
            alerts.append(
                the_alert(self, source, destinations[0] if destinations else None, window.latest, evidence)
            )
        return alerts


def window_seconds(window: Window) -> float:
    """How long the attempts in the window took."""
    if not window.attempts:
        return 0.0
    first = min(attempt.started for attempt in window.attempts)
    last = max(attempt.started for attempt in window.attempts)
    return round(max(0.0, last - first), 3)


def the_default_rules(thresholds: Thresholds | None = None) -> list[Rule]:
    """The rules the sentinel runs when it is not told otherwise."""
    limits = thresholds or Thresholds()
    return [
        PortSweepRule(limits),
        HalfOpenScanRule(limits),
        SilentConnectionRule(limits),
        ServiceProbeRule(limits),
    ]
