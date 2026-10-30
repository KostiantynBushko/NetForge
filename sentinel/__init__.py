"""The sentinel: what is happening on the network.

The sentinel watches, and says.  It watches two things -- the traffic
on an interface, and the logs the machines write -- and it says the
same kind of thing about both: that one address was looking at a lot
of ports, or that one address failed to log in a lot of times.

The package holds four operations:

``sentinel.network.analyse``
    reads a capture file and reports the scans in it;

``sentinel.network.monitor``
    watches an interface while it runs, and writes the capture it made;

``sentinel.log.analyse``
    reads the logs of a host and reports the scans in them;

``sentinel.alert.list``
    reads the alerts back out of the file they are kept in.

The engine is the same in all of them: a window of connection attempts,
and rules that read the window.  The rules are plain classes over that
window, so each one can be read on its own and tested on its own.
"""

from __future__ import annotations

from netforge.sentinel.alerts import (
    Alert,
    AlertListOperation,
    AlertListRequest,
    AlertListResponse,
    Severity,
    read_alerts,
    write_alerts,
)
from netforge.sentinel.engine import (
    Attempt,
    Rule,
    Sentinel,
    Thresholds,
    Window,
)
from netforge.sentinel.logs import (
    LogAnalysisOperation,
    LogAnalysisRequest,
    LogAnalysisResponse,
    LogEvent,
    parse_access_log,
    parse_syslog,
    parse_ufw,
    the_log_rules,
)
from netforge.sentinel.network import (
    NetworkAnalysisOperation,
    NetworkAnalysisRequest,
    NetworkAnalysisResponse,
    NetworkMonitorOperation,
    NetworkMonitorRequest,
    NetworkMonitorResponse,
)
from netforge.sentinel.rules import (
    HalfOpenScanRule,
    PortSweepRule,
    ServiceProbeRule,
    SilentConnectionRule,
    the_default_rules,
)

__all__ = [
    "Alert",
    "AlertListOperation",
    "AlertListRequest",
    "AlertListResponse",
    "Attempt",
    "HalfOpenScanRule",
    "LogAnalysisOperation",
    "LogAnalysisRequest",
    "LogAnalysisResponse",
    "LogEvent",
    "NetworkAnalysisOperation",
    "NetworkAnalysisRequest",
    "NetworkAnalysisResponse",
    "NetworkMonitorOperation",
    "NetworkMonitorRequest",
    "NetworkMonitorResponse",
    "PortSweepRule",
    "Rule",
    "Sentinel",
    "ServiceProbeRule",
    "Severity",
    "SilentConnectionRule",
    "Thresholds",
    "Window",
    "parse_access_log",
    "parse_syslog",
    "parse_ufw",
    "read_alerts",
    "the_default_rules",
    "the_log_rules",
    "write_alerts",
]
