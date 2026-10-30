# `analysis.flow`

> Analyse a capture file and report the conversations it contains.

**Risk:** Safe (level 1)  
**Category:** analysis  
**Tags:** `analysis`, `flow`, `pcap`, `traffic`  
**Implementation:** `netforge.analysis.flow:FlowAnalysisOperation`

---

## What it does

Reads a libpcap capture file, aggregates its packets into flows and reports the largest conversations with their sizes, their durations and the TCP flags they carried. The file is only read, so the operation is declared at the safe level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `path` | string | — | **Required.** The path of the capture file to analyse. |
| `top` | integer | `50` | How many flows to report. (at least 1, at most 10000) |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `path` | string | The path of the capture file that was read. |
| `flows` | list of object | The conversations of the capture, as a list of dictionaries. |
| `statistics` | object | The statistics of the capture: the totals and the sizes. |

## Using it

### From the command line

```console
$ netforge run analysis.flow --path <string>
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("analysis.flow")
result = await operation.run(path=...)
```

## How it works

Flow analysis of capture files.

This module implements a libpcap reader and a flow aggregator on the
standard library alone.  That is a deliberate choice: the analysis of a
capture file is one of the things NetForge is *for*, and making it depend
on a packet library would put a third-party requirement in the middle of
the framework's core value.

The reader understands the two link types that matter in practice:

* ``LINKTYPE_ETHERNET`` (1) -- Ethernet II frames;
* ``LINKTYPE_RAW`` (101) -- bare IP packets;
* ``LINKTYPE_LINUX_SLL`` (113) -- the "cooked" capture Linux produces.

and the IPv4/IPv6, TCP/UDP/ICMP headers on top of them.

## See also

* [the `analysis` package](README.md) — every operation it publishes
* [the architecture](../ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../README.md)
