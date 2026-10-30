# The NetForge documentation

This folder is the entry point to everything NetForge is documented in.

Every package has a **folder of its own, inside the package**: the entry
point of the package, and one page per operation. The architecture
document explains how the modules fit together and why; the package
documents explain what each one does.

The documentation lives with the code it describes — `connectivity/docs/`
belongs to `connectivity/` — so that a package and its documentation are
never apart.

---

## Start here

| Document | What it answers |
|---|---|
| [The architecture](ARCHITECTURE.md) | How is the code put together, and why? Where does each principle live? |
| [Getting started](../README.md) | How do I install it and run it? |

---

## The capability packages

These ten packages publish the thirty operations that `netforge list`
prints. Each has a folder of its own, inside the package: the entry point
is the `README.md` of the folder, and every operation it publishes has a
page of its own.

| Package | Operations | What it is for | Entry point |
|---|---|---|---|
| `netforge.connectivity` | 4 | Reaching remote systems: SSH, HTTP, TCP, UDP. | [connectivity](../connectivity/docs/README.md) |
| `netforge.discovery` | 6 | What is out there: ping, sweeps, traceroute, ARP, routes, services. | [discovery](../discovery/docs/README.md) |
| `netforge.dns` | 2 | Resolving names, and diagnosing the SPF and DMARC policies that live in DNS. | [dns](../dns/docs/README.md) |
| `netforge.protocols` | 5 | Speaking the wire protocols: HTTP, SNMP, Modbus TCP, MQTT, OPC UA. | [protocols](../protocols/docs/README.md) |
| `netforge.capture` | 1 | Capturing traffic into a libpcap file. | [capture](../capture/docs/README.md) |
| `netforge.analysis` | 1 | Reading a capture back and reporting what it means. | [analysis](../analysis/docs/README.md) |
| `netforge.configuration` | 4 | Reading, checking, comparing and writing a device's configuration. | [configuration](../configuration/docs/README.md) |
| `netforge.security` | 4 | Assessment and diagnostics: port scanning, banners, TLS, security headers. | [security](../security/docs/README.md) |
| `netforge.manipulation` | 1 | Controlled modification of traffic, through a proxy. | [manipulation](../manipulation/docs/README.md) |
| `netforge.emulation` | 2 | Simulating the network a device is on. | [emulation](../emulation/docs/README.md) |

---

## The framework

These four modules make NetForge a framework rather than a script. They
depend on Pydantic and the standard library, and on nothing else. They
publish no operations, so they have no operation pages — but their
documentation lives in their own folder too, the same way.

| Module | What it is for | Document |
|---|---|---|
| `netforge.core` | The operation contract, the execution context, the configuration, the exception hierarchy, the command runner and the native seam. | [core.md](../core/docs/README.md) |
| `netforge.models` | Every model that crosses a boundary: requests, responses, execution metadata, risk levels and capability categories. | [models.md](../models/docs/README.md) |
| `netforge.registry` | The catalogue. The only source of truth about what NetForge can do. | [registry.md](../registry/docs/README.md) |
| `netforge.plugins` | The extension point. How a third party adds operations. | [plugins.md](../plugins/docs/README.md) |

---

## The adapter layer

One contract, four renderings of the same catalogue.

| Module | What it is for | Document |
|---|---|---|
| `netforge.adapters` | The command line, the REST API, MCP and LlamaIndex. Every adapter reads the registry; none of them reimplements a capability. | [adapters.md](../adapters/docs/README.md) |

---

## How the documents are organised

Every package page follows the same shape, so that reading one tells you
how to read the next:

1. **What the package is for** — the problem it solves.
2. **Operations** — what it publishes, at which risk level, with a link
   to the page of each.
3. **The API** — the names it exports, with their signatures.
4. **Using it** — a short example that runs.
5. **Notes** — dependencies, side effects and the details that bite.

Every operation page follows the same shape:

1. **What it does** — the summary and the full description.
2. **The request** — every parameter, with its type, its default and
   what it is.
3. **The response** — every field the operation returns.
4. **Using it** — from the command line and from Python.
5. **How it works** — the implementation notes, from the module itself.

---

## The documentation is generated

The operation pages, the operations table and the API listing are
**derived from the code**: the registry is the only source of truth about
what NetForge can do, and the code already carries the prose — the
module docstrings, the operation docstrings and the field descriptions
that become the request schema.

`tools/generate_docs.py` writes them. The prose around them is
hand-written and is never touched: the generator replaces only what is
between `<!-- generated:... -->` markers.

```bash
python tools/generate_docs.py           # write what is out of date
python tools/generate_docs.py --check   # fail when something is stale
```

`tests/test_documentation.py` asserts that the documentation matches the
registry, that every package has its entry point, that the top-level
README links to every one of them, and that every link in this folder
resolves.

---

## Conventions used here

* The import path is always `netforge.<module>`, even though the source
  directory is `<module>/` at the root of the repository. The project root
  *is* the `netforge` package; `pyproject.toml` maps it back under that
  name when the distribution is built.
* Risk levels are written as `Safe`, `Observability`, `Manipulation` and
  `System Modification` — the four levels of the model described in
  [the architecture](ARCHITECTURE.md#the-risk-model).
* Every operation is asynchronous. `await operation.run(...)` is the
  normal way to invoke one, whether you are using the CLI, the REST API
  or the Python SDK.
