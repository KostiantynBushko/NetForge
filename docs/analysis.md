# `netforge.analysis`

Analysis reads what was captured and reports what it means: the flows, the
protocols, the sizes.

Everything in this package is read-only, so every operation is declared at
the safe risk level.

---

## Operations

| Operation | Risk | What it does |
|---|---|---|
| `analysis.flow` | Safe | Analyse a capture file and report the conversations it contains. |

---

## Reading a capture

`read_pcap(path)` reads a libpcap file and returns its packets. It is a
pure function over the file — the standard library `struct` module, no
third-party parser.

It recognises the four link types NetForge cares about: Ethernet, raw IP
and the two Linux "cooked" variants, identified by the file's magic
number. A file that is not a libpcap raises `ValueError` with the magic it
found.

```python
from netforge.analysis import read_pcap

packets = read_pcap("/tmp/capture.pcap")
packets[0].source, packets[0].destination, packets[0].protocol
```

`Packet` is one decoded packet: `timestamp`, `length`, `protocol`,
`source`, `destination`, `source_port`, `destination_port` and `info`.

---

## The analyzer

`FlowAnalyzer(*, top=50)` aggregates the packets of a capture file into
flows.

`Flow` is one aggregated conversation: `source`, `destination`,
`source_port`, `destination_port`, `protocol`, `packets`, `bytes`,
`first_seen`, `last_seen` and the TCP `flags` seen.

`top` bounds how many flows are reported, so a capture with a hundred
thousand conversations does not produce a hundred thousand lines of
output.

---

## The request and response

`FlowAnalysisRequest(*, path, top=50)` — `path` is required, `top` is
between 1 and 10000.

`FlowAnalysisResponse` reports `path`, the `flows` as a list of
dictionaries, and `statistics`.

---

## Using it

```python
operation = registry.create("analysis.flow")
result = await operation.run(path="/tmp/capture.pcap", top=20)

for flow in result.flows:
    print(flow["source"], "->", flow["destination"], flow["bytes"], "bytes")
```

---

## The public API

```text
class Flow                             (source, destination, source_port, destination_port,
                                        protocol, packets=0, bytes=0, first_seen=0.0,
                                        last_seen=0.0, flags=set())
class FlowAnalysisOperation
class FlowAnalysisRequest              (*, path, top=50)
class FlowAnalysisResponse             (*, operation='', risk_level='', duration_ms=0.0,
                                        warnings=[], path, flows=[], statistics={})
class FlowAnalyzer                     (*, top=50)
class Packet                           (timestamp, length, protocol='', source='',
                                        destination='', source_port=None,
                                        destination_port=None, info='')

read_pcap(path) -> list[Packet]
```

---

## Notes

* IP fragmentation is not reassembled. The reader handles the link layer
  and the IP header, and stops there.
* The reader is deliberately free of `scapy` and of every other capture
  library: the format is documented, and parsing it is a hundred lines of
  `struct`.
* See also: [the architecture](ARCHITECTURE.md), [capture.md](capture.md).
