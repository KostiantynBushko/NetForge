# `netforge.discovery`

Discovery answers "what is out there?". It covers ping, ping sweeps,
traceroute, ARP and route tables, and service discovery.

The parsers are separated from the operations on purpose.
`/proc/net/arp` and `/proc/net/route` are plain text with a documented
format, and their parsers are pure functions over text — so they can be
tested against a captured sample without a Linux kernel, and without root.

---

## Operations

| Operation | Risk | What it does |
|---|---|---|
| `discovery.ping` | Safe | Send ICMP echo requests to a host and report the round-trip times. |
| `discovery.ping.sweep` | Observability | Ping every address of a network and report the hosts that answer. |
| `discovery.traceroute` | Safe | Trace the network path to a host and report every hop. |
| `discovery.arp.table` | Safe | Read the local ARP neighbour table. |
| `discovery.route.table` | Safe | Read the local routing table. |
| `discovery.service.enumerate` | Observability | Probe the ports of a host and name the services that are listening. |

A single ping is safe — one host, one request, and the answer is the
point. A sweep is one level higher: a whole subnet notices.

---

## The parsers

Both are pure functions over text, and both are exported.

```python
from netforge.discovery import parse_arp_table, parse_route_table

entries = parse_arp_table(open("/proc/net/arp").read())
entries[0].ip_address, entries[0].mac_address, entries[0].device
```

| Function | Reads | Returns |
|---|---|---|
| `parse_arp_table(text)` | the contents of `/proc/net/arp` | a list of `ArpEntry` |
| `parse_route_table(text)` | the contents of `/proc/net/route` | a list of `RouteEntry` |

`ArpEntry` is `ip_address`, `hw_type`, `flags`, `mac_address`, `device`.
`RouteEntry` is `destination`, `gateway`, `netmask`, `device`, `metric`,
`flags`, `protocol`.

Because they are pure, the test suite feeds them a captured sample and
checks the answer. No kernel, no root, no network.

---

## The ping result

`PingResult` is the parsed result of one ping: `reachable`, `loss_percent`,
`min_ms`, `avg_ms`, `max_ms` and the `raw` output.

---

## The sweep

`PingSweepOperation` pings every address of a network and reports the
hosts that answer. It is the one operation in this package that composes
with `asyncio.gather` — hundreds of probes run concurrently, which is why
the framework is async first.

---

## Using it

```python
from netforge.discovery import parse_arp_table

entries = parse_arp_table(open("/proc/net/arp").read())
for entry in entries:
    print(entry.ip_address, entry.mac_address, entry.device)
```

Through the framework:

```python
operation = registry.create("discovery.ping")
result = await operation.run(host="10.0.0.1", count=4)
```

---

## The public API

```text
class ArpEntry                     (ip_address, hw_type, flags, mac_address, device)
class ArpTableOperation
class PingOperation
class PingResult                   (reachable, loss_percent=100.0, min_ms=None,
                                    avg_ms=None, max_ms=None, raw='')
class PingSweepOperation
class RouteEntry                   (destination, gateway, netmask, device,
                                    metric=0, flags=0, protocol='')
class RouteTableOperation
class ServiceDiscoveryOperation
class TracerouteOperation

parse_arp_table(text) -> list[ArpEntry]
parse_route_table(text) -> list[RouteEntry]
```

---

## Notes

* `ping`, `traceroute` and the sweep shell out to the system tools through
  `context.command_runner`. That is what makes them testable offline, and
  it is why the tools need to be installed for them to work at runtime.
* The ARP and route operations read the local tables, so they report the
  machine NetForge runs on — not a remote host.
* `discovery.service.enumerate` probes ports and names what it finds; it
  is the discovery counterpart of
  [the port scanner](security.md#the-port-scanner).
* See also: [the architecture](ARCHITECTURE.md),
  [security.md](security.md), [connectivity.md](connectivity.md).
