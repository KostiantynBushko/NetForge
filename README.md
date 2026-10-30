# NetForge

> A modular network operations and security toolkit. One implementation of a
> capability, available through Python, a command line, a REST API, MCP and
> LlamaIndex function tools.

NetForge is a **framework first**. The networking logic never depends on an AI
framework, and the framework itself depends on nothing but Pydantic and the
standard library. Every ecosystem integration is an optional extra, so the
toolkit installs and runs on a bare Python.

```text
                        NetForge API
                             │
                             ▼
                      Python Framework
                             │
             ┌───────────────┼───────────────┐
             ▼               ▼               ▼
        Python          Rust Module      C++ Module
      Implementation     Implementation   Implementation
```

---

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

# the integrations you want
pip install -e '.[all]'
```

The core needs Python 3.11 or newer.

| Extra | What it adds |
|---|---|
| `rest` | the REST API (`fastapi`, `uvicorn`) |
| `mcp` | the MCP server (`mcp`) |
| `llamaindex` | the LlamaIndex function tools (`llama-index-core`) |
| `ssh` | the SSH connection (`asyncssh`) |
| `dns` | the DNS record types that need a real query (`dnspython`) |
| `mqtt` | the MQTT broker client (`paho-mqtt`) |
| `opcua` | the OPC UA session (`asyncua`) |
| `all` | everything above |

An extra that is missing never breaks the framework: the capability is still
listed, and running it says exactly what to install.

---

## The command line

The CLI is always available — it is built on `argparse` and needs no extra.

```bash
netforge list                       # the catalogue, grouped by category
netforge list --category security   # one category
netforge list --json                # the catalogue as JSON
netforge describe discovery.ping    # one operation, with its request schema
netforge categories                 # the capability categories
netforge risk                       # the risk profile of the catalogue
netforge run discovery.ping --request '{"host": "10.0.0.1"}'
netforge serve rest --port 8080     # start another adapter
```

`--max-risk` is a ceiling for the whole command:

```bash
netforge --max-risk 2 list          # only what a level-2 caller may run
netforge --max-risk 1 run configuration.restore --request '{}'
# RiskPolicyError: operation 'configuration.restore' is declared at risk level 4 ...
```

---

## The Python API

```python
import asyncio
from netforge import ExecutionContext, load_builtin_operations

registry = load_builtin_operations()
operation = registry.create("discovery.ping")

response = asyncio.run(operation.run(host="10.0.0.1", count=3))
print(response.reachable, response.avg_ms)
```

Every operation is strongly typed, so the request is validated before
anything happens:

```python
from pydantic import ValidationError

try:
    asyncio.run(operation.run(host="10.0.0.1", timout=3))
except ValidationError as exc:
    print(exc)      # 'timout' is not a field -- the typo is reported
```

---

## The risk model

Every operation declares a risk level, and the framework enforces it. The
level is part of the operation's identity: it is published in the registry,
enforced by the execution context and rendered by every adapter.

| Level | Name | Meaning | Examples |
|---|---|---|---|
| 1 | Safe | Read-only information gathering. | ping, DNS lookup, traceroute |
| 2 | Observability | Monitoring and traffic observation. | packet capture, port scan, service discovery |
| 3 | Manipulation | Operations capable of affecting traffic behaviour. | proxying, packet modification, a remote command |
| 4 | System Modification | Operations that modify system or network state. | configuration deployment, `tc`, firewall changes |

The ceiling comes from the configuration and from the caller's context:

```bash
export NETFORGE_MAX_RISK=2      # never run above level 2
```

```python
from netforge import ExecutionContext, RiskLevel

context = ExecutionContext(max_risk=RiskLevel.OBSERVABILITY)
```

An operation that is above the ceiling is refused *before* its request is
even looked at, and the refusal is its own exception type — `RiskPolicyError`
— so a caller can tell "that does not exist" from "that exists and I am not
allowed to run it".

---

## The architecture

The framework is a set of packages, one per capability:

```text
.
├── core/          the framework: operation contract, context, config, runner
├── models/        the Pydantic contracts: requests, responses, risk, categories
├── registry/      the catalogue of everything NetForge can do
├── connectivity/  SSH, HTTP, WebSocket, TCP, UDP
├── discovery/     ping, sweeps, traceroute, ARP, routes, services
├── dns/           resolution, SPF and DMARC diagnostics
├── protocols/     HTTP, MQTT, SNMP, Modbus TCP, OPC UA
├── capture/       packet capture sessions and BPF filters
├── analysis/      libpcap reading and flow analysis
├── configuration/ validate, diff, back up and restore a device's configuration
├── security/      port scanning, banners, TLS inspection, header analysis
├── manipulation/  TCP proxying
├── emulation/     network condition profiles and `tc`
├── adapters/      CLI, REST, MCP, LlamaIndex
└── plugins/       the plugin system
```

The capability packages sit at the top of the repository: the project root
*is* the `netforge` package. `pyproject.toml` maps it back under that name
when the distribution is built, so `import netforge` resolves exactly as it
would from any installed copy.

The rule that keeps it coherent: **the registry is the only catalogue**.
Every adapter reads from it, so a capability implemented once is available
through every adapter without a second implementation.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design in detail and
[NetForge.md](NetForge.md) for the specification it implements. Every module
has its own document as well — start at [the documentation index](docs/README.md).

---

## The adapters

| Adapter | Extra | What it exposes |
|---|---|---|
| `cli` | — | the catalogue and the operations |
| `rest` | `rest` | `GET /operations`, `POST /operations/{name}`, … |
| `mcp` | `mcp` | every operation as an MCP tool |
| `llamaindex` | `llamaindex` | every operation as a `FunctionTool` |

```bash
netforge serve rest --host 127.0.0.1 --port 8080
netforge serve mcp
netforge serve llamaindex
```

An adapter is never partial: it exposes the whole catalogue or it is not
available.

---

## Plugins

A plugin adds operations to the registry. It is discovered through the
`netforge.plugins` entry point group, or through a directory:

```python
from netforge.plugins import PluginManager

manager = PluginManager(registry)
manager.load_all(directories=["/opt/netforge-plugins"])
print(manager.describe())
print(manager.failures)
```

A plugin that fails to load is reported and skipped. It never takes the
framework down — a broken third-party plugin must not stop an operator from
running `ping`.

---

## Native acceleration

The specification allows a performance-critical module to be reimplemented
in Rust or C++ while the public API stays identical. The seam for that is
`netforge.core.native`:

```python
from netforge.core.native import NativeImplementation, native_registry

native_registry.register(
    NativeImplementation(
        operation="analysis.flow",
        language="rust",
        entrypoint=rust_flow_analyzer,
        version="0.1.0",
    )
)
```

The caller never learns which implementation served an operation.

---

## Documentation

[docs/README.md](docs/README.md) is the entry point to everything NetForge
is documented in. Every package has a **folder of its own, inside the
package** — the entry point of the package, and one page per operation —
and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) explains how the modules
fit together and why.

### The capability packages

These are the ten packages `netforge list` prints, and the thirty
operations they publish. The documentation of each one is in its own
folder, inside the package.

| Package | Operations | What it is for | Documentation |
|---|---|---|---|
| `netforge.connectivity` | 4 | Reaching remote systems: SSH, HTTP, TCP, UDP. | [connectivity](connectivity/docs/README.md) |
| `netforge.discovery` | 6 | What is out there: ping, sweeps, traceroute, ARP, routes, services. | [discovery](discovery/docs/README.md) |
| `netforge.dns` | 2 | Resolving names, and diagnosing the SPF and DMARC policies. | [dns](dns/docs/README.md) |
| `netforge.protocols` | 5 | Speaking the wire protocols: HTTP, SNMP, Modbus TCP, MQTT, OPC UA. | [protocols](protocols/docs/README.md) |
| `netforge.capture` | 1 | Capturing traffic into a libpcap file. | [capture](capture/docs/README.md) |
| `netforge.analysis` | 1 | Reading a capture back and reporting what it means. | [analysis](analysis/docs/README.md) |
| `netforge.configuration` | 4 | Reading, checking, comparing and writing a device's configuration. | [configuration](configuration/docs/README.md) |
| `netforge.security` | 4 | Assessment and diagnostics: port scanning, banners, TLS, security headers. | [security](security/docs/README.md) |
| `netforge.manipulation` | 1 | Controlled modification of traffic, through a proxy. | [manipulation](manipulation/docs/README.md) |
| `netforge.emulation` | 2 | Simulating the network a device is on. | [emulation](emulation/docs/README.md) |

### The framework

| | |
|---|---|
| [The architecture](docs/ARCHITECTURE.md) | how the code is put together, and why |
| [The core](core/docs/README.md) | the operation contract, the context, the configuration |
| [The models](models/docs/README.md) | every model that crosses a boundary |
| [The registry](registry/docs/README.md) | the catalogue — the only source of truth |
| [The plugins](plugins/docs/README.md) | the extension point |
| [The adapters](adapters/docs/README.md) | the CLI, the REST API, MCP and LlamaIndex |

---

## Tests

```bash
python -m pytest -q
```

The suite is offline: it needs neither the network, nor the system tools,
nor root. The capabilities that shell out are driven through an injected
command runner, and the ones that open sockets are driven against a local
server the test itself starts.

---

## Licence

MIT. See [LICENSE](LICENSE).
