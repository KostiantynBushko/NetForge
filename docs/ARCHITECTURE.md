# The architecture of NetForge

This document explains how the code is put together and why. The
specification it implements is [NetForge.md](../NetForge.md); this is the
translation of that specification into a package layout.

---

## The five principles, and where they live

### Framework first

Networking logic must never depend on an AI framework.

The core of NetForge — `netforge.core`, `netforge.models`,
`netforge.registry` — imports Pydantic and the standard library. Nothing
else. There is no `llama_index` import anywhere below `netforge.adapters`,
and the adapter imports are optional and lazy.

The evidence is mechanical: `pip install netforge` pulls in exactly one
package, and every capability module imports only what it needs.

### Adapter driven

AI integrations are adapter layers built on top of the core framework.

Every adapter reads the same source — `netforge.registry.OperationRegistry` —
and renders it in its own way. There is no per-adapter list of
capabilities, because a list would drift.

### Async first

All public operations support asynchronous execution.

`Operation.execute()` is a coroutine, even when the operation does nothing
but read a file. The calling code does not change shape when an operation
becomes slow, and the whole framework composes with `asyncio.gather` — which
is how the ping sweep runs hundreds of probes concurrently.

### Strongly typed

All requests and responses use Pydantic models.

An operation declares `request_model` and `response_model` as class
attributes. The registry publishes them as JSON Schema; the REST adapter
validates against them; the MCP and LlamaIndex adapters derive their tool
signatures from them.

The base model forbids unknown fields, so a typo is an error rather than a
silently ignored key. It does **not** strip whitespace, because a request
that carries a configuration or a certificate must arrive byte for byte.

### Extensible

New functionality is provided through plugins and operation registration.

`netforge.plugins` discovers plugins through the `netforge.plugins` entry
point group or through a directory. A plugin is a class with a name, a
version and a list of operations.

### Reusable

Every capability is available through the Python SDK, the CLI, the REST API,
MCP and LlamaIndex — without duplicating implementation logic.

This is the property the rest of the design exists to serve.

---

## The layers

```text
┌──────────────────────────────────────────────────────────────┐
│  adapters/      cli · rest · mcp · llamaindex                │
├──────────────────────────────────────────────────────────────┤
│  registry/      the catalogue — the only source of truth     │
├──────────────────────────────────────────────────────────────┤
│  capability     connectivity · discovery · dns · protocols    │
│  packages       capture · analysis · configuration ·          │
│                 security · manipulation · emulation           │
├──────────────────────────────────────────────────────────────┤
│  core/          operation · context · config · runner · native│
│  models/        request · response · risk · category          │
└──────────────────────────────────────────────────────────────┘
```

Each layer only knows about the one below it. A capability package never
imports an adapter; an adapter never reimplements a capability.

---

## The operation contract

`netforge.core.operation.Operation` is the unit of work.

```python
class PingOperation(Operation[PingRequest, PingResponse]):
    name = "discovery.ping"
    category = CapabilityCategory.DISCOVERY
    risk_level = RiskLevel.SAFE
    summary = "Send ICMP echo requests to a host and report the round-trip times."

    request_model = PingRequest
    response_model = PingResponse

    async def execute(self, request: PingRequest, context: ExecutionContext) -> PingResponse:
        ...
```

Three things are enforced by the framework rather than by convention:

**Async.** `execute()` is a coroutine.

**Typed.** The request and response models are declared, and the registry
publishes their JSON Schema.

**A declared risk level.** `Operation.__init_subclass__` refuses to create a
concrete operation that has not declared its name, its category, its risk
level and its two models. "The risk level is missing" cannot reach
production — it is a `TypeError` at class-definition time.

### The execution order

```text
run_request(payload, context)
        │
        ├── context.check_risk(...)      ← the ceiling is enforced first
        ├── request_model.model_validate(payload)
        └── execute(request, context)
```

The risk check comes *before* the validation, deliberately: an operation
that is above the ceiling is refused whatever its payload says, and the
refusal does not depend on the payload being well formed.

---

## The execution context

`netforge.core.context.ExecutionContext` carries what an operation cannot
decide for itself:

| Field | Meaning |
|---|---|
| `config` | the framework configuration |
| `max_risk` | the ceiling this caller may run at |
| `credentials` | named secrets, resolved lazily |
| `timeout` | the time budget |
| `dry_run` | report the action without performing it |
| `command_runner` | the injected runner, for the capabilities that shell out |

The `command_runner` is what makes the discovery and emulation capabilities
testable. `ping`, `traceroute` and `tc` are driven through it, so the test
suite needs neither the system tools nor the network.

---

## The registry

`netforge.registry.OperationRegistry` is the catalogue.

```python
registry = load_builtin_operations()
registry.names()                       # every operation name, sorted
registry.list(category="security")     # filtered
registry.list(max_risk=RiskLevel.SAFE) # filtered by ceiling
registry.get("discovery.ping")         # the descriptor
registry.create("discovery.ping")      # an instance
```

A descriptor carries the name, the category, the risk level, the summary,
the tags and the two JSON Schemas. It is the published form of an operation,
and it is what the adapters render.

The registry is deliberately boring: a mapping from a name to a descriptor
and the class behind it. It is created empty, filled by the bootstrap and by
plugins, and then it is read.

---

## The risk model

The four levels are the ones in the specification. `RiskLevel` is an
`IntEnum`, because risk comparison is ordinal — "is this at or below the
ceiling?" — and an integer comparison says that most clearly.

The ceiling is enforced in three places, and all three matter:

1. the **configuration** (`NETFORGE_MAX_RISK`) — the machine's policy;
2. the **context** — the caller's policy;
3. the **operation** — the declaration.

The effective ceiling is the stricter of the first two. The third is always
checked.

---

## The adapters

An adapter has a small contract:

* `available()` — is it usable in this installation?
* `describe()` — what is it, and what can it do?
* the catalogue, and the ability to invoke an operation.

The CLI is built on `argparse` and is always available. The REST, MCP and
LlamaIndex adapters import their extra lazily and report, in
`unavailable_reason()`, exactly what is missing and how to install it.

An adapter is never partial: it exposes the whole catalogue or it is not
available. A tool that works for some capabilities and silently does not
work for others is worse than no tool.

---

## The plugin system

```python
class MyPlugin(Plugin):
    name = "my-plugin"
    version = "1.0.0"

    def operations(self) -> list[type[Operation]]:
        return [MyOperation]
```

The manager discovers plugins through the `netforge.plugins` entry point
group or through a directory of packages, instantiates them and registers
their operations.

Every loader collects its failures instead of raising them. A plugin that
cannot be imported is reported in `manager.failures` and skipped. That is a
deliberate choice: a broken third-party plugin must not be able to stop an
operator from running `ping`.

---

## The native seam

`netforge.core.native` is where a Rust or C++ implementation would take
over.

```python
native_registry.register(
    NativeImplementation(
        operation="analysis.flow",
        language="rust",
        entrypoint=rust_flow_analyzer,
    )
)
```

The caller never learns which implementation served the operation — that is
the API stability requirement of the specification, and it is why the seam
is a single registry rather than a set of `if` statements spread across the
capability packages.

---

## What is deliberately not implemented

Some things are named in the specification and are not in the code. They are
listed here rather than left to be discovered.

| Capability | Why |
|---|---|
| SNMPv3 | needs USM — key derivation and message digests. v1 and v2c are implemented. |
| OPC UA sessions | the binary protocol needs a client library; `asyncua` is the optional extra. The endpoint *parser* is implemented. |
| MQTT broker sessions | needs a client library; `paho-mqtt` is the optional extra. The topic *matcher* is implemented. |
| IP fragmentation in the pcap reader | the reader handles Ethernet, raw IP and Linux "cooked" captures. |
| WiFi, Bluetooth and USB transports | the specification's examples for emulation are network conditions, which are covered by the profiles. |

In every case the *hard* part — the part that is worth having exactly
right and that can be tested offline — is implemented, and the part that
needs a third-party library is an optional extra.
