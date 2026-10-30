# `netforge.sentinel`

The sentinel watches, and says. It watches two things — the traffic on
an interface, and the logs the machines write — and it says the same
kind of thing about both: that one address was looking at a lot of
ports, or that one address failed to log in a lot of times.

Everything it reports is a **suspicion**, not a proof. A host that
answers ten ports in a second may be a scanner, or it may be a
monitoring agent, or it may be a misconfiguration. The severity says
how much to believe it, and the evidence is there so that a person can.

---

## Operations

<!-- generated:operations -->
| Operation | Risk | What it does |
|---|---|---|
| [`sentinel.alert.list`](alert.list.md) | Safe | Read the alerts out of the file the sentinel keeps them in. |
| [`sentinel.log.analyse`](log.analyse.md) | Safe | Read the logs of a host and report the scans in them. |
| [`sentinel.network.analyse`](network.analyse.md) | Safe | Read a capture file and report the scans that are in it. |
| [`sentinel.network.monitor`](network.monitor.md) | Observability | Watch an interface and report the scans that go past. |
<!-- /generated:operations -->

---

## The engine

A scan is not one event. It is many small ones — a SYN here, a RST
there, ten ports in a second — and none of them means anything on its
own. What makes it a scan is the *shape*: one address, many ports, in a
short time.

So the engine keeps a **window** of what it has seen, and the rules read
the window. The unit is the **attempt**: one address trying to reach
one port.

| The attempt is | Which means |
|---|---|
| open | the handshake finished, so the port was open |
| reset | the port answered with a reset, so it was closed |
| pending | nobody answered at all |
| silent | neither side said anything once the handshake was done |
| probed | the source spoke first, which is what a probe does |

The window is measured in the clock of the capture, not in the clock of
the machine. A file analysed today says the same thing as the same file
analysed tomorrow, and a monitor that is watching says the same thing as
the file it would have written.

---

## The rules

| Rule | What it finds | Severity |
|---|---|---|
| `port-sweep` | one address touched many ports of another in a short time | High |
| `half-open-scan` | many ports refused without the handshake completing — nmap's `-sS` | High |
| `silent-connections` | many connections that said nothing at all — the native scanner | Medium |
| `service-probe` | a payload where the service should have spoken first — nmap's `-sV` | Medium |

Every threshold is a parameter of the request, so a quiet network can be
given a longer window and a higher count than a busy one.

A rule that fires is reported **once**: a sweep that lasts ten minutes
is one finding, not six hundred.

---

## The log half

A capture is not the only record of a scan. The host that was scanned
usually wrote it down as well — in the authentication log, in the
firewall's log, in the web server's access log. Those records are
already there, they need no privilege to read, and they survive the
monitor being stopped.

The parsers are the interesting part. Each format has its own parser,
and each parser is a pure function over a text:

| Parser | Reads |
|---|---|
| `parse_syslog(text)` | the authentication events of a syslog or auth log |
| `parse_ufw(text)` | the blocked connections of a UFW log |
| `parse_access_log(text)` | the requests of an nginx or Apache access log |

What they produce is the same thing — a `LogEvent` — and the rules are
written against the event, never against the format. A rule that knows
about a burst of failed logins does not care whether it read them from
sshd or from journald, and a new format is a new parser, with no rule
to change.

| Rule | What it finds | Severity |
|---|---|---|
| `ssh-failure-burst` | one address failed to authenticate many times | High |
| `firewall-port-sweep` | one address was refused on many ports by the firewall | High |
| `web-scan` | one address made many requests that were refused | Medium |

`firewall-port-sweep` is the cheapest detector there is: the host was
already writing the log.

---

## The alerts

An alert is a named event with the evidence behind it. The evidence is
what makes an alert worth reading: "ten ports in a second" is a number,
"ten ports in a second, and here they are" is a finding.

The alerts are kept in a JSON Lines file — one JSON object per line,
appended as they are found. The file is opened for appending, so a
monitor that is restarted does not lose the alerts it found before.

```bash
netforge run sentinel.alert.list --path /var/lib/netforge/alerts.jsonl
```

---

## Using it

Reading a capture that has already been made:

```bash
netforge run sentinel.network.analyse --path /tmp/capture.pcap
```

Watching an interface while it runs:

```bash
sudo netforge run sentinel.network.monitor \
  --interface wlo1 --duration 3600 \
  --output /var/lib/netforge/live.pcap \
  --sink /var/lib/netforge/alerts.jsonl
```

Reading the logs of a host:

```bash
netforge run sentinel.log.analyse --path /var/log/auth.log
```

The monitor is a convenience; the analyser is the truth. A capture is a
record, and a record can be read again — so the monitor writes the
capture it made, and the same traffic can be read afterwards with
`sentinel.network.analyse`.

---

## The public API

<!-- generated:public-api -->
```text
class Alert(*, rule: str, severity: str = 'medium', summary: str, source: str = '', destination: str | None = None, timestamp: float = 0.0, evidence: dict[str, typing.Any] = {})
class AlertListOperation()
class AlertListRequest(*, path: str, since: float | None = None, severity: str | None = None, rule: str | None = None, limit: int = 100)
class AlertListResponse(*, operation: str = '', risk_level: str = '', duration_ms: float = 0.0, warnings: list[str] = [], path: str, alerts: list[netforge.sentinel.alerts.Alert] = [], total: int = 0, by_severity: dict[str, int] = {}, by_rule: dict[str, int] = {})
class Attempt(source: str, destination: str, source_port: int, destination_port: int, protocol: str = 'tcp', started: float = 0.0, completed: bool = False, reset: bool = False, payload_from_source: int = 0, payload_from_target: int = 0, packets: int = 0)
class HalfOpenScanRule(thresholds: Thresholds | None = None)
class LogAnalysisOperation()
class LogAnalysisRequest(*, path: str, format: str = 'auto', window_seconds: float = 300.0, failures: int = 10, blocked_ports: int = 10, errors: int = 20)
class LogAnalysisResponse(*, operation: str = '', risk_level: str = '', duration_ms: float = 0.0, warnings: list[str] = [], path: str, alerts: list[netforge.sentinel.alerts.Alert] = [], events: int = 0, files: int = 0)
class LogEvent(timestamp: float, action: str, service: str = '', source: str | None = None, destination: str | None = None, port: int | None = None, user: str | None = None, path: str | None = None, status: int | None = None, message: str = '', raw: str = '')
class NetworkAnalysisOperation()
class NetworkAnalysisRequest(*, path: str, window_seconds: float = 60.0, distinct_ports: int = 10, half_open: int = 5, silent_handshakes: int = 10, service_probes: int = 3)
class NetworkAnalysisResponse(*, operation: str = '', risk_level: str = '', duration_ms: float = 0.0, warnings: list[str] = [], path: str, alerts: list[netforge.sentinel.alerts.Alert] = [], packets: int = 0, attempts: int = 0, sources: int = 0)
class NetworkMonitorOperation()
class NetworkMonitorRequest(*, interface: str = 'any', duration: float = 60.0, expression: str | None = None, output: str | None = None, sink: str | None = None, snaplen: int = 65535, window_seconds: float = 60.0, distinct_ports: int = 10, half_open: int = 5, silent_handshakes: int = 10, service_probes: int = 3)
class NetworkMonitorResponse(*, operation: str = '', risk_level: str = '', duration_ms: float = 0.0, warnings: list[str] = [], interface: str, alerts: list[netforge.sentinel.alerts.Alert] = [], packets: int = 0, attempts: int = 0, output: str | None = None, sink: str | None = None, duration_seconds: float = 0.0)
class PortSweepRule(thresholds: Thresholds | None = None)
class Rule(args, kwargs)
class Sentinel(*, window_seconds: float = 60.0, rules: Iterable[Rule] | None = None, thresholds: Thresholds | None = None)
class ServiceProbeRule(thresholds: Thresholds | None = None)
class Severity()
class SilentConnectionRule(thresholds: Thresholds | None = None)
class Thresholds(*, distinct_ports: int = 10, half_open: int = 5, silent_handshakes: int = 10, service_probes: int = 3)
class Window(attempts: list[Attempt] = <factory>, latest: float = 0.0)
def parse_access_log(text: str) -> list[LogEvent]
def parse_syslog(text: str) -> list[LogEvent]
def parse_ufw(text: str) -> list[LogEvent]
def read_alerts(path: str | Path, *, since: float | None = None, severity: str | Severity | None = None, rule: str | None = None) -> list[Alert]
def the_default_rules(thresholds: Thresholds | None = None) -> list[Rule]
def the_log_rules(failures: int, ports: int, errors: int) -> list[LogRule]
def write_alerts(path: str | Path, alerts: Iterable[Alert]) -> int
```
<!-- /generated:public-api -->

---

## Notes

**The privilege.** The monitor opens a raw socket, so it needs root or
`setcap cap_net_raw+ep` on the capture tool. The analyser and the log
reader need nothing: they only read files.

**The thresholds fight the levels.** The scans of NetForge come in five
levels, from `paranoid` to `aggressive` (see
[the discovery package](../../discovery/docs/README.md#the-engines-and-the-levels)).
A `paranoid` scan spreads its probes over seconds, so a detector with a
one-second window sees too little to notice it. The window has to be
chosen against the quietest scan you intend to catch, not the loudest.

**Your own scans trip your own rules.** A port sweep is a port sweep,
whoever made it. If the sentinel watches the machine that runs the
scans, expect to be told about them.

**The two halves see different things.** The network half sees a scan
as it happens; the log half sees it afterwards, and sees things the
capture never held — a password spray that was refused every time, and
left no open port to find.
