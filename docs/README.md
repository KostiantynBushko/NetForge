# The NetForge documentation

This folder is the entry point to everything NetForge is documented in.

There is one document per module. Each one describes what the module is
for, the operations it publishes, the names it exports and how to use it
from Python. The architecture document explains how the modules fit
together and why; the module documents explain what each one does.

---

## Start here

| Document | What it answers |
|---|---|
| [The architecture](ARCHITECTURE.md) | How is the code put together, and why? Where does each principle live? |
| [Getting started](../README.md) | How do I install it and run it? |

---

## The framework

These four modules make NetForge a framework rather than a script. They
depend on Pydantic and the standard library, and on nothing else.

| Module | What it is for | Document |
|---|---|---|
| `netforge.core` | The operation contract, the execution context, the configuration, the exception hierarchy, the command runner and the native seam. | [core.md](core.md) |
| `netforge.models` | Every model that crosses a boundary: requests, responses, execution metadata, risk levels and capability categories. | [models.md](models.md) |
| `netforge.registry` | The catalogue. The only source of truth about what NetForge can do. | [registry.md](registry.md) |
| `netforge.plugins` | The extension point. How a third party adds operations. | [plugins.md](plugins.md) |

---

## The adapter layer

One contract, four renderings of the same catalogue.

| Module | What it is for | Document |
|---|---|---|
| `netforge.adapters` | The command line, the REST API, MCP and LlamaIndex. Every adapter reads the registry; none of them reimplements a capability. | [adapters.md](adapters.md) |

---

## The capability packages

Each package implements one kind of network work, and publishes operations
that any adapter can then expose.

| Module | Operations | What it is for | Document |
|---|---|---|---|
| `netforge.connectivity` | 4 | Reaching remote systems: SSH, HTTP, WebSocket, TCP, UDP. | [connectivity.md](connectivity.md) |
| `netforge.discovery` | 6 | What is out there: ping, sweeps, traceroute, ARP, routes, services. | [discovery.md](discovery.md) |
| `netforge.dns` | 2 | Resolving names, and diagnosing the SPF and DMARC policies that live in DNS. | [dns.md](dns.md) |
| `netforge.protocols` | 5 | Speaking the wire protocols: HTTP, SNMP, Modbus TCP, MQTT, OPC UA. | [protocols.md](protocols.md) |
| `netforge.capture` | 1 | Capturing traffic into a libpcap file. | [capture.md](capture.md) |
| `netforge.analysis` | 1 | Reading a capture back and reporting what it means. | [analysis.md](analysis.md) |
| `netforge.configuration` | 4 | Reading, checking, comparing and writing a device's configuration. | [configuration.md](configuration.md) |
| `netforge.security` | 4 | Assessment and diagnostics: port scanning, banners, TLS, security headers. | [security.md](security.md) |
| `netforge.manipulation` | 1 | Controlled modification of traffic, through a proxy. | [manipulation.md](manipulation.md) |
| `netforge.emulation` | 2 | Simulating the network a device is on. | [emulation.md](emulation.md) |

Thirty operations in total. `netforge list` prints them at runtime, grouped
by category.

---

## How the documents are organised

Every module document follows the same shape, so that reading one tells
you how to read the next:

1. **What the module is for** — the problem it solves.
2. **Operations** — what it publishes, at which risk level.
3. **The public API** — the names it exports, with their signatures.
4. **Using it** — a short example that runs.
5. **Notes** — dependencies, side effects and the details that bite.

---

## Conventions used here

* The import path is always `netforge.<module>`, even though the source
  directory is `<module>/` at the root of the repository. The project root
  *is* the `netforge` package; `pyproject.toml` maps it back under that
  name when the distribution is built.
* Risk levels are written as `Safe`, `Observability`, `Manipulation` and
  `System modification` — the four levels of the model described in
  [the architecture](ARCHITECTURE.md#the-risk-model).
* Every operation is asynchronous. `await operation.run(...)` is the
  normal way to invoke one, whether you are using the CLI, the REST API
  or the Python SDK.
