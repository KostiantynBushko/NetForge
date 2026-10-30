# `netforge.core`

The core of NetForge: the operation contract, the execution context, the
configuration, the exception hierarchy, the command runner, the logging
helpers and the native seam.

It has no dependency on any capability package and no dependency on any
adapter. Everything below the adapter layer is built on this, and this
depends on Pydantic and the standard library only.

---

## The operation contract

`Operation` is the unit of work. An operation declares its name, its
category, its risk level, its two models and a summary, and implements
`execute()`.

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

* **Async** — `execute()` is a coroutine, always.
* **Typed** — the request and response models are declared, and the
  registry publishes their JSON Schema.
* **A declared risk level** — `Operation.__init_subclass__` refuses to
  create a concrete operation that has not declared its name, its category,
  its risk level and its two models. A missing risk level is a `TypeError`
  at class-definition time, not a production surprise.

---

## The execution context

`ExecutionContext` carries what an operation cannot decide for itself.

| Field | Meaning |
|---|---|
| `config` | the framework configuration |
| `max_risk` | the ceiling this caller may run at |
| `credentials` | named secrets, resolved lazily |
| `timeout` | the time budget |
| `dry_run` | report the action without performing it |
| `metadata` | anything else the caller wants to pass down |
| `command_runner` | the injected runner, for the capabilities that shell out |

The `command_runner` is what makes the discovery and emulation capabilities
testable. `ping`, `traceroute` and `tc` are driven through it, so the test
suite needs neither the system tools nor the network.

---

## The configuration

`NetForgeConfig` is a Pydantic model, and every field can be set from the
environment with the `NETFORGE_` prefix.

| Field | Default | Environment variable |
|---|---|---|
| `default_timeout` | `30.0` | `NETFORGE_DEFAULT_TIMEOUT` |
| `max_risk` | `RiskLevel.SYSTEM_MODIFICATION` | `NETFORGE_MAX_RISK` |
| `log_level` | `"INFO"` | `NETFORGE_LOG_LEVEL` |
| `verify_tls` | `True` | `NETFORGE_VERIFY_TLS` |
| `user_agent` | `"netforge/0.1.0"` | `NETFORGE_USER_AGENT` |
| `capture_directory` | `Path("captures")` | `NETFORGE_CAPTURE_DIRECTORY` |
| `allow_native` | `True` | `NETFORGE_ALLOW_NATIVE` |

`ENV_PREFIX` is exported for callers that need to build the variable names
themselves.

---

## The exception hierarchy

Everything NetForge raises deliberately descends from `NetForgeError`, so a
caller can catch the framework's failures with one `except` clause and
still let anything else through.

```text
NetForgeError
├── ConfigurationError      the framework was configured with something it cannot use
├── DependencyMissingError  an optional dependency for this capability is not installed
├── OperationNotFoundError  no operation is registered under the requested name
├── OperationExecutionError an operation was invoked and failed
├── RiskPolicyError         the operation is above the risk ceiling the caller allowed
├── TimeoutError            an operation exceeded its time budget
└── PluginError             a plugin could not be loaded
```

`DependencyMissingError` is the one that matters most in practice: it names
the dependency and the extra that provides it, so a missing optional
integration reports what to install rather than an `ImportError`.

It accepts more than one dependency, and names them all in the same
message. That matters when a single extra provides several packages: a
user told about one package at a time has to run the command again after
each installation, to be told about the next one.

```python
DependencyMissingError(["fastapi", "uvicorn"], extra="rest", feature="serving the REST adapter")
# the optional dependencies 'fastapi' and 'uvicorn' are required for
# serving the REST adapter. Install it with: pip install 'netforge[rest]'
```

---

## The command runner

`CommandRunner` is the interface a command runner must provide.
`SubprocessCommandRunner` is the implementation that spawns real
processes, and `CommandResult` is what comes back.

```python
result = await context.command_runner.run(["ping", "-c", "1", host])
result.returncode, result.stdout, result.stderr, result.duration_ms
```

Injecting a runner is how the suite exercises `ping`, `traceroute` and `tc`
without the system tools and without the network.

---

## Logging

`get_logger(name)` returns the logger for a module — `get_logger("core.runner")`
— and `configure_logging(level)` sets up the `netforge` logger and returns
it.

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

The caller never learns which implementation served the operation. That is
the API stability requirement of the specification, and it is why the seam
is a single registry rather than a set of `if` statements spread across
the capability packages.

`NativeRegistry` and `native_registry` are the registry and its
singleton; `NativeImplementation` is one registered implementation.

---

## The public API

```text
class CommandResult(argv, returncode, stdout='', stderr='', duration_ms=0.0, env={})
class CommandRunner
class ConfigurationError(NetForgeError)
class Credential(name, username=None, secret=None, metadata={})
class DependencyMissingError(NetForgeError)      (dependency, extra=None, feature='')
                                                 dependency may be one name or a list
class ExecutionContext(config=..., max_risk=..., credentials={}, timeout=None,
                       dry_run=False, metadata={}, command_runner=None)
class NetForgeConfig                              (*, default_timeout=30.0, max_risk=...,
                                                 log_level='INFO', verify_tls=True,
                                                 user_agent='netforge/0.1.0',
                                                 capture_directory=Path('captures'),
                                                 allow_native=True)
class NetForgeError(Exception)
class NativeImplementation(operation, language, entrypoint, version='unknown')
class NativeRegistry
class Operation
class OperationExecutionError(NetForgeError)
class OperationNotFoundError(NetForgeError)       (name, available=None)
class PluginError(NetForgeError)
class RiskPolicyError(NetForgeError)              (operation, risk_level, ceiling)
class SubprocessCommandRunner                     (*, default_timeout=30.0)
class TimeoutError(NetForgeError)

ENV_PREFIX = "NETFORGE_"
configure_logging(level='INFO', *, stream=None, fmt=...) -> logging.Logger
get_logger(name=None) -> logging.Logger
native_registry -> NativeRegistry
```

---

## Notes

* `netforge.core` imports nothing outside the standard library and
  Pydantic. That is the "framework first" principle, and it is the reason
  `pip install netforge` pulls in exactly one package.
* The `Operation` base class is generic: `Operation[PingRequest,
  PingResponse]` binds the two models for the type checker.
* See also: [the architecture](ARCHITECTURE.md), [models.md](models.md),
  [registry.md](registry.md).
