# `netforge.emulation`

Simulating the network a device is on: the latency, the jitter, the loss
and the bandwidth.

The profiles are pure data; applying them changes the machine's own
network, which is why the operation that does it is declared at the system
modification level.

---

## Operations

<!-- generated:operations -->
| Operation | Risk | What it does |
|---|---|---|
| [`emulation.netem`](netem.md) | System Modification | Apply, reset or show the network conditions of an interface. |
| [`emulation.profile`](profile.md) | Safe | Describe a network profile or list the built-in presets. |
<!-- /generated:operations -->

Describing a profile reads nothing and changes nothing. Applying one
rewrites the kernel's queueing discipline on an interface, which is why
the two operations sit at opposite ends of the risk model.

---

## The profiles

`NetworkProfile(name, latency_ms=0.0, jitter_ms=0.0, loss_percent=0.0,
bandwidth_mbps=None, description='')` is a description of the conditions
to simulate.

`PROFILE_PRESETS` is the table of built-in profiles — a dictionary of
name to `NetworkProfile`:

| Preset | Latency | Jitter | Loss | Bandwidth |
|---|---|---|---|---|
| `clean` | 1 ms | 0.2 ms | 0 % | 1000 Mbit/s |
| `cellular` | 60 ms | 30 ms | 0.5 % | 25 Mbit/s |
| `bad_wifi` | 120 ms | 80 ms | 3 % | 8 Mbit/s |
| `satellite` | 650 ms | 40 ms | 0.2 % | 100 Mbit/s |
| `constrained_iot` | 900 ms | 200 ms | 5 % | 0.1 Mbit/s |

`grade_profile(profile)` returns the problems with a profile, as a list of
strings. It is a pure function.

```python
from netforge.emulation import PROFILE_PRESETS, grade_profile

profile = PROFILE_PRESETS["cellular"]
print(profile.latency_ms, profile.loss_percent)      # 60.0 0.5
print(grade_profile(profile))
```

---

## Applying a profile

`build_netem_command(interface, profile, *, root=True)` builds the `tc`
command line that applies a profile. It returns the argument list, and it
does not run anything — so the command can be inspected, logged or run
under a different runner.

```python
from netforge.emulation import build_netem_command

build_netem_command("eth0", PROFILE_PRESETS["cellular"])
# ['tc', 'qdisc', 'replace', 'dev', 'eth0', 'root', 'netem',
#  'delay 60.000ms 30.000ms', 'loss 0.500%', 'rate', '25.000mbit']
```

`NetEmController(interface)` applies and removes the network conditions on
an interface — `apply()`, `reset()` and `show()`.

`parse_qdisc(text)` parses the output of `tc qdisc show` into a list of
dictionaries. It is a pure function over text, so it can be tested against
a captured sample.

---

## Using it

```python
operation = registry.create("emulation.netem")
result = await operation.run(interface="eth0", profile="3g", action="apply")
```

---

## The public API

<!-- generated:public-api -->
```text
class NetEmController(interface: str)
class NetEmOperation()
class NetworkProfile(name: str, latency_ms: float = 0.0, jitter_ms: float = 0.0, loss_percent: float = 0.0, bandwidth_mbps: float | None = None, description: str = '')
PROFILE_PRESETS = {'bad_wifi': NetworkProfile(name='bad_wifi', latency_ms=1...
class ProfileOperation()
def build_netem_command(interface: str, profile: NetworkProfile, *, root: bool = True) -> list[str]
def grade_profile(profile: NetworkProfile) -> list[str]
def parse_qdisc(text: str) -> list[dict[str, str]]
```
<!-- /generated:public-api -->

---

## Notes

* Applying a profile needs `tc` — the `iproute2` package on most systems —
  and enough privileges to write to the interface, usually root.
* `emulation.netem` changes the machine NetForge runs on. It is the reason
  the risk model has a fourth level at all.
* `grade_profile` catches the combinations that do not make sense — a
  bandwidth limit with no delay, a loss percentage above a hundred — before
  they reach the kernel.
* See also: [the architecture](../ARCHITECTURE.md),
  [manipulation.md](../manipulation/README.md), [discovery.md](../discovery/README.md).
