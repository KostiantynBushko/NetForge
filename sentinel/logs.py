"""The log half: reading what the machines already wrote down.

A packet capture is not the only record of a scan.  The host that was
scanned usually wrote the scan down as well -- in the authentication
log, in the firewall's log, in the web server's access log.  Those
records are already there, they need no privilege to read, and they
survive the monitor being stopped.

The parsers are the interesting part.  Each format has its own parser,
and each parser is a pure function over a text.  What they produce is
the same thing: a :class:`LogEvent`.  The rules are written against the
event, never against the format, so a rule that knows about a burst of
failed logins does not care whether it read them from sshd or from
journald -- and a new format is a new parser, with no rule to change.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel
from netforge.sentinel.alerts import Alert, Severity

__all__ = [
    "LogEvent",
    "parse_syslog",
    "parse_ufw",
    "parse_access_log",
    "the_log_rules",
    "LogAnalysisRequest",
    "LogAnalysisResponse",
    "LogAnalysisOperation",
]

_logger = get_logger("sentinel.logs")

#: The month names, in the order they appear in a syslog timestamp.
MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

#: ``Jan 12 10:15:03 host sshd[1234]: the message``
SYSLOG_LINE = re.compile(
    r"^(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+(?P<program>[^:\[]+)(?:\[(?P<pid>\d+)\])?:\s*(?P<message>.*)$"
)

#: ``... Failed password for bob from 10.0.0.5 port 5678 ssh2``
FAILED_PASSWORD = re.compile(
    r"Failed password for (?:invalid user )?(?P<user>\S+) from (?P<source>\S+)"
)
INVALID_USER = re.compile(r"Invalid user (?P<user>\S+) from (?P<source>\S+)")
ACCEPTED = re.compile(
    r"Accepted (?P<method>\S+) for (?P<user>\S+) from (?P<source>\S+)"
)

#: ``... [UFW BLOCK] IN=eth0 OUT= SRC=10.0.0.5 DST=10.0.0.2 PROTO=TCP SPT=1 DPT=22``
UFW_LINE = re.compile(r"\[UFW (?P<action>[A-Z]+)\](?P<fields>.*)$")
UFW_FIELD = re.compile(r"(?P<name>[A-Z]+)=(?P<value>\S*)")

#: ``10.0.0.5 - - [12/Jan/2024:10:15:03 +0000] "GET /admin HTTP/1.1" 404 123 ...``
ACCESS_LINE = re.compile(
    r"^(?P<source>\S+)\s+\S+\s+(?P<user>\S+)\s+"
    r"\[(?P<timestamp>[^\]]+)\]\s+"
    r'"(?P<method>[A-Z]+)\s+(?P<path>\S+)[^"]*"\s+'
    r"(?P<status>\d{3})\s+(?P<size>\S+)"
)


@dataclass(frozen=True, slots=True)
class LogEvent:
    """One thing that happened, as the logs recorded it."""

    timestamp: float
    action: str
    service: str = ""
    source: str | None = None
    destination: str | None = None
    port: int | None = None
    user: str | None = None
    path: str | None = None
    status: int | None = None
    message: str = ""
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return the event as a plain dictionary."""
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "service": self.service,
            "source": self.source,
            "destination": self.destination,
            "port": self.port,
            "user": self.user,
            "path": self.path,
            "status": self.status,
            "message": self.message,
        }


def _the_syslog_timestamp(month: str, day: str, clock: str, year: int | None = None) -> float:
    """The timestamp of a syslog line.

    A syslog timestamp carries no year, so the year of the line is the
    year of the machine that wrote it.  A log that spans new year is
    the one case this gets wrong.
    """
    moment = datetime(
        year or datetime.now().year,
        MONTHS.get(month, 1),
        int(day),
        int(clock[0:2]),
        int(clock[3:5]),
        int(clock[6:8]),
        tzinfo=UTC,
    )
    return moment.timestamp()


def parse_syslog(text: str) -> list[LogEvent]:
    """Read the authentication events out of a syslog or auth log.

    Only the events that say something about a login are read: a failed
    password, an unknown user, an accepted one.  The rest of the log is
    left alone.
    """
    events: list[LogEvent] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        header = SYSLOG_LINE.match(line)
        if header is None:
            continue
        message = header.group("message")
        program = header.group("program")

        match = FAILED_PASSWORD.search(message)
        if match:
            events.append(
                LogEvent(
                    timestamp=_the_syslog_timestamp(
                        header.group("month"), header.group("day"), header.group("time")
                    ),
                    action="failed-password",
                    service=program,
                    source=match.group("source"),
                    user=match.group("user"),
                    message=message,
                    raw=line,
                )
            )
            continue

        match = INVALID_USER.search(message)
        if match:
            events.append(
                LogEvent(
                    timestamp=_the_syslog_timestamp(
                        header.group("month"), header.group("day"), header.group("time")
                    ),
                    action="invalid-user",
                    service=program,
                    source=match.group("source"),
                    user=match.group("user"),
                    message=message,
                    raw=line,
                )
            )
            continue

        match = ACCEPTED.search(message)
        if match:
            events.append(
                LogEvent(
                    timestamp=_the_syslog_timestamp(
                        header.group("month"), header.group("day"), header.group("time")
                    ),
                    action="accepted",
                    service=program,
                    source=match.group("source"),
                    user=match.group("user"),
                    message=message,
                    raw=line,
                )
            )
    return events


def parse_ufw(text: str) -> list[LogEvent]:
    """Read the blocked connections out of a UFW log."""
    events: list[LogEvent] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        header = SYSLOG_LINE.match(line)
        if header is None:
            continue
        match = UFW_LINE.search(header.group("message"))
        if match is None:
            continue
        fields = {
            found.group("name"): found.group("value")
            for found in UFW_FIELD.finditer(match.group("fields"))
        }
        port = fields.get("DPT")
        events.append(
            LogEvent(
                timestamp=_the_syslog_timestamp(
                    header.group("month"), header.group("day"), header.group("time")
                ),
                action=match.group("action").lower(),
                service="ufw",
                source=fields.get("SRC"),
                destination=fields.get("DST"),
                port=int(port) if port and port.isdigit() else None,
                message=header.group("message"),
                raw=line,
            )
        )
    return events


def parse_access_log(text: str) -> list[LogEvent]:
    """Read the requests out of an nginx or Apache access log."""
    events: list[LogEvent] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = ACCESS_LINE.match(line)
        if match is None:
            continue
        try:
            moment = datetime.strptime(
                match.group("timestamp"), "%d/%b/%Y:%H:%M:%S %z"
            )
        except ValueError:
            continue
        events.append(
            LogEvent(
                timestamp=moment.timestamp(),
                action="request",
                service="http",
                source=match.group("source"),
                user=None if match.group("user") == "-" else match.group("user"),
                path=match.group("path"),
                status=int(match.group("status")),
                message=line,
                raw=line,
            )
        )
    return events


def the_parsers() -> dict[str, Any]:
    """The parsers, by the name they are asked for."""
    return {
        "syslog": parse_syslog,
        "ufw": parse_ufw,
        "access": parse_access_log,
    }


class LogRule:
    """A rule over the events of a log."""

    name = ""
    severity = Severity.MEDIUM.value
    summary = ""

    def evaluate(self, events: list[LogEvent]) -> list[Alert]:
        """Return the alerts the events hold."""
        raise NotImplementedError


class SshFailureBurstRule(LogRule):
    """Many failed logins from one address.

    The oldest and the most useful of the log rules: a password spray
    is a handful of failures against many accounts, and a brute force
    is many failures against one.
    """

    name = "ssh-failure-burst"
    severity = Severity.HIGH.value
    summary = "One address failed to authenticate many times."

    def __init__(self, failures: int = 10) -> None:
        self.failures = failures

    def evaluate(self, events: list[LogEvent]) -> list[Alert]:
        """Look for a source with many failed logins."""
        by_source: dict[str, list[LogEvent]] = {}
        for event in events:
            if event.action not in ("failed-password", "invalid-user"):
                continue
            if not event.source:
                continue
            by_source.setdefault(event.source, []).append(event)

        alerts: list[Alert] = []
        for source, failures in by_source.items():
            if len(failures) < self.failures:
                continue
            users = sorted({event.user for event in failures if event.user})
            evidence: dict[str, Any] = {
                "failures": len(failures),
                "users": users,
                "first": min(event.timestamp for event in failures),
                "last": max(event.timestamp for event in failures),
            }
            alerts.append(
                Alert(
                    rule=self.name,
                    severity=self.severity,
                    summary=self.summary,
                    source=source,
                    timestamp=max(event.timestamp for event in failures),
                    evidence=evidence,
                )
            )
        return alerts


class FirewallPortSweepRule(LogRule):
    """Many destination ports refused from one address.

    This is the port sweep as the firewall saw it: every closed port
    answered with a rejection, and the rejections all came from the same
    address.  It is the cheapest detector there is, because the host
    was already writing the log.
    """

    name = "firewall-port-sweep"
    severity = Severity.HIGH.value
    summary = "One address was refused on many ports by the firewall."

    def __init__(self, ports: int = 10) -> None:
        self.ports = ports

    def evaluate(self, events: list[LogEvent]) -> list[Alert]:
        """Look for a source that was refused on many ports."""
        by_source: dict[str, set[int]] = {}
        for event in events:
            if event.action not in ("block", "reject", "blocked"):
                continue
            if not event.source or event.port is None:
                continue
            by_source.setdefault(event.source, set()).add(event.port)

        alerts: list[Alert] = []
        for source, ports in by_source.items():
            if len(ports) < self.ports:
                continue
            evidence: dict[str, Any] = {
                "refused_ports": len(ports),
                "ports": sorted(ports),
            }
            alerts.append(
                Alert(
                    rule=self.name,
                    severity=self.severity,
                    summary=self.summary,
                    source=source,
                    timestamp=time.time(),
                    evidence=evidence,
                )
            )
        return alerts


class WebScanRule(LogRule):
    """Many refused requests from one address.

    A crawler looks for pages and gets 404s; a scanner looks for pages
    that should not be there.  The difference is the rate and the
    variety of the paths.
    """

    name = "web-scan"
    severity = Severity.MEDIUM.value
    summary = "One address made many requests that were refused."

    def __init__(self, errors: int = 20) -> None:
        self.errors = errors

    def evaluate(self, events: list[LogEvent]) -> list[Alert]:
        """Look for a source with many refused requests."""
        by_source: dict[str, list[LogEvent]] = {}
        for event in events:
            if event.status is None or event.status < 400:
                continue
            if not event.source:
                continue
            by_source.setdefault(event.source, []).append(event)

        alerts: list[Alert] = []
        for source, errors in by_source.items():
            if len(errors) < self.errors:
                continue
            evidence: dict[str, Any] = {
                "errors": len(errors),
                "paths": sorted({event.path for event in errors if event.path})[:50],
                "statuses": sorted({event.status for event in errors if event.status}),
            }
            alerts.append(
                Alert(
                    rule=self.name,
                    severity=self.severity,
                    summary=self.summary,
                    source=source,
                    timestamp=max(event.timestamp for event in errors),
                    evidence=evidence,
                )
            )
        return alerts


def the_log_rules(failures: int, ports: int, errors: int) -> list[LogRule]:
    """The rules the log analyser runs."""
    return [
        SshFailureBurstRule(failures),
        FirewallPortSweepRule(ports),
        WebScanRule(errors),
    ]


class LogAnalysisRequest(RequestModel):
    """Request of :class:`LogAnalysisOperation`."""

    path: str = Field(description="The log file to read, or a directory of them.")
    format: str = Field(
        default="auto",
        description="The format of the log: auto, syslog, ufw or access.",
    )
    window_seconds: float = Field(
        default=300.0, gt=0.0, description="The window the rules look at."
    )
    failures: int = Field(default=10, ge=1, description="How many failed logins make a burst.")
    blocked_ports: int = Field(
        default=10, ge=1, description="How many refused ports make a sweep."
    )
    errors: int = Field(default=20, ge=1, description="How many refused requests make a scan.")


class LogAnalysisResponse(ResponseModel):
    """Response of :class:`LogAnalysisOperation`."""

    path: str = Field(description="The log that was read.")
    alerts: list[Alert] = Field(default_factory=list, description="What was found.")
    events: int = Field(default=0, description="How many events were read.")
    files: int = Field(default=0, description="How many files were read.")
    duration_ms: float = Field(default=0.0, description="How long the analysis took.")


class LogAnalysisOperation(Operation[LogAnalysisRequest, LogAnalysisResponse]):
    """Read the logs and report the scans in them."""

    name = "sentinel.log.analyse"
    category = CapabilityCategory.SECURITY
    risk_level = RiskLevel.SAFE
    summary = "Read the logs of a host and report the scans in them."
    description = (
        "Reads the authentication, firewall and web server logs of a host and reports "
        "what they say about scans: a burst of failed logins, a sweep refused by the "
        "firewall, and a run of requests that were refused. The logs are only read, "
        "so the operation is declared at the safe level."
    )
    tags = frozenset({"detection", "logs", "auth", "firewall", "forensics"})

    request_model = LogAnalysisRequest
    response_model = LogAnalysisResponse

    async def execute(
        self, request: LogAnalysisRequest, context: ExecutionContext
    ) -> LogAnalysisResponse:
        """Read the logs and report what they say."""
        started = time.perf_counter()
        target = Path(request.path)
        if not target.exists():
            return LogAnalysisResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                path=request.path,
                warnings=[f"{target} does not exist"],
            )

        files = sorted(target.rglob("*")) if target.is_dir() else [target]
        files = [path for path in files if path.is_file()]
        if not files:
            return LogAnalysisResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                path=request.path,
                warnings=[f"{target} holds no files"],
            )

        parsers = the_parsers()
        chosen = list(parsers.values()) if request.format == "auto" else [parsers[request.format]]

        events: list[LogEvent] = []
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                _logger.warning("the log %s could not be read: %s", path, exc)
                continue
            for parser in chosen:
                events.extend(parser(text))

        # Only the events of the window are of interest.
        if events:
            newest = max(event.timestamp for event in events)
            events = [
                event for event in events if event.timestamp >= newest - request.window_seconds
            ]

        alerts: list[Alert] = []
        for rule in the_log_rules(request.failures, request.blocked_ports, request.errors):
            alerts.extend(rule.evaluate(events))

        return LogAnalysisResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            path=request.path,
            alerts=alerts,
            events=len(events),
            files=len(files),
        )
