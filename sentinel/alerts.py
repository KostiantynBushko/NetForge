"""The alerts, and the file they are kept in.

An alert is a named event with the evidence behind it.  The evidence is
what makes an alert worth reading: "ten ports in a second" is a number,
"ten ports in a second, and here they are" is a finding.

The alerts are kept in a JSON Lines file: one JSON object per line,
appended as they are found.  The format is plain enough to grep, and
plain enough for another program to read without a schema.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.operation import Operation
from netforge.models.base import NetForgeModel, RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = [
    "Severity",
    "Alert",
    "write_alerts",
    "read_alerts",
    "AlertListRequest",
    "AlertListResponse",
    "AlertListOperation",
]


class Severity(StrEnum):
    """How much an alert matters."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def label(self) -> str:
        """The human-readable name of the severity."""
        return self.name.title()

    @property
    def rank(self) -> int:
        """The severity as a number, so that the levels can be compared."""
        return list(Severity).index(self)

    @classmethod
    def parse(cls, value: str | Severity) -> Severity:
        """Coerce ``value`` into a :class:`Severity`."""
        if isinstance(value, cls):
            return value
        text = str(value).strip().lower()
        try:
            return cls(text)
        except ValueError as exc:
            raise ValueError(f"unknown severity: {value!r}") from exc


class Alert(NetForgeModel):
    """Something that was seen, and why it was thought to be worth saying."""

    rule: str = Field(description="The rule that fired.")
    severity: str = Field(default=Severity.MEDIUM.value, description="How much it matters.")
    summary: str = Field(description="A one-line description of what happened.")
    source: str = Field(default="", description="The address the activity came from.")
    destination: str | None = Field(default=None, description="The address it was aimed at.")
    timestamp: float = Field(default=0.0, description="When it happened, as a Unix timestamp.")
    evidence: dict[str, Any] = Field(
        default_factory=dict, description="What the rule saw."
    )

    def to_line(self) -> str:
        """Return the alert as one line of JSON."""
        return json.dumps(self.model_dump(), sort_keys=True)


def write_alerts(path: str | Path, alerts: Iterable[Alert]) -> int:
    """Append the alerts to the sink, and return how many were written.

    The file is opened for appending, so a monitor that is restarted
    does not lose the alerts it found before.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with target.open("a", encoding="utf-8") as handle:
        for alert in alerts:
            handle.write(alert.to_line() + "\n")
            written += 1
    return written


def read_alerts(
    path: str | Path,
    *,
    since: float | None = None,
    severity: str | Severity | None = None,
    rule: str | None = None,
) -> list[Alert]:
    """Read the alerts back from the sink.

    A line that cannot be read is skipped: the sink is appended to while
    it is being read, and a half-written line is not a reason to lose
    the rest.
    """
    target = Path(path)
    if not target.exists():
        return []

    wanted = Severity.parse(severity) if severity is not None else None
    alerts: list[Alert] = []
    for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            alert = Alert.model_validate(json.loads(line))
        except (ValueError, json.JSONDecodeError):
            continue
        if since is not None and alert.timestamp < since:
            continue
        if wanted is not None and Severity.parse(alert.severity) is not wanted:
            continue
        if rule is not None and alert.rule != rule:
            continue
        alerts.append(alert)
    return alerts


class AlertListRequest(RequestModel):
    """Request of :class:`AlertListOperation`."""

    path: str = Field(description="The sink the alerts are kept in.")
    since: float | None = Field(
        default=None, description="Only the alerts after this Unix timestamp."
    )
    severity: str | None = Field(
        default=None, description="Only the alerts of this severity."
    )
    rule: str | None = Field(default=None, description="Only the alerts of this rule.")
    limit: int = Field(default=100, ge=1, le=10000, description="How many alerts to report.")


class AlertListResponse(ResponseModel):
    """Response of :class:`AlertListOperation`."""

    path: str = Field(description="The sink that was read.")
    alerts: list[Alert] = Field(default_factory=list, description="The alerts.")
    total: int = Field(default=0, description="How many alerts the sink holds.")
    by_severity: dict[str, int] = Field(
        default_factory=dict, description="How many alerts of each severity."
    )
    by_rule: dict[str, int] = Field(
        default_factory=dict, description="How many alerts of each rule."
    )


class AlertListOperation(Operation[AlertListRequest, AlertListResponse]):
    """Read the alerts back out of the sink."""

    name = "sentinel.alert.list"
    category = CapabilityCategory.SECURITY
    risk_level = RiskLevel.SAFE
    summary = "Read the alerts out of the file the sentinel keeps them in."
    description = (
        "Reads the alerts the sentinel has written, and reports them newest last, with "
        "a count of how many there are of each severity and of each rule. The file is "
        "only read, so the operation is declared at the safe level."
    )
    tags = frozenset({"detection", "alerts", "report"})

    request_model = AlertListRequest
    response_model = AlertListResponse

    async def execute(
        self, request: AlertListRequest, context: ExecutionContext
    ) -> AlertListResponse:
        """Read the alerts."""
        alerts = read_alerts(
            request.path,
            since=request.since,
            severity=request.severity,
            rule=request.rule,
        )
        by_severity: dict[str, int] = {}
        by_rule: dict[str, int] = {}
        for alert in alerts:
            by_severity[alert.severity] = by_severity.get(alert.severity, 0) + 1
            by_rule[alert.rule] = by_rule.get(alert.rule, 0) + 1

        return AlertListResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            path=request.path,
            alerts=alerts[-request.limit:],
            total=len(alerts),
            by_severity=dict(sorted(by_severity.items())),
            by_rule=dict(sorted(by_rule.items())),
        )
