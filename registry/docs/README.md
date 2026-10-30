# `netforge.registry`

The registry is the catalogue of everything NetForge can do. Adapters read
from it; nothing else is a source of truth.

---

## Why it is the only catalogue

Every adapter renders the same registry in a different way — the CLI prints
it, the REST API serves it, MCP turns it into tools, LlamaIndex turns it
into function tools. There is no per-adapter list of capabilities, because
a list would drift.

If you are adding an operation, you are adding it to the registry. If you
are writing an adapter, you are reading from it.

---

## Using it

```python
from netforge.core.bootstrap import load_builtin_operations

registry = load_builtin_operations()

registry.names()                        # every operation name, sorted
registry.list()                         # every descriptor
registry.list(category="security")      # filtered by category
registry.list(max_risk=RiskLevel.SAFE)  # filtered by ceiling
registry.list(tag="ssh")                # filtered by tag
registry.list(query="dns")              # filtered by a text search
registry.get("discovery.ping")          # the descriptor
registry.create("discovery.ping")       # an instance
```

The registry is deliberately boring: a mapping from a name to a descriptor
and the class behind it. It is created empty, filled by the bootstrap and
by plugins, and then it is read.

---

## The descriptor

`OperationDescriptor` is the published metadata of one operation — the form
the adapters render.

| Field | Meaning |
|---|---|
| `name` | the operation's name, e.g. `discovery.ping` |
| `category` | its `CapabilityCategory` |
| `risk_level` | the level it is declared at |
| `summary` | one line, for a list |
| `description` | the long form |
| `tags` | free-form labels for filtering |
| `aliases` | alternative names |
| `requires_privilege` | whether it needs root or a capability |
| `request_schema` | the JSON Schema of the request model |
| `response_schema` | the JSON Schema of the response model |
| `implementation` | `"module:Operation"`, or the native implementation |

`descriptors_as_dicts(registry)` returns the registry's descriptors as
plain dictionaries — the shape the REST API serves.

---

## Registering an operation

An operation is registered by its module, through
`registry.register_module(module)`, which inspects the module and picks up
every `Operation` subclass it finds. That is what
`load_builtin_operations()` does for each of the built-in capability
modules, in a fixed order.

A plugin registers its operations the same way — see
[plugins.md](../../plugins/docs/README.md).

---

## The public API

```text
class OperationDescriptor                      (*, name, category, risk_level,
                                                summary='', description='',
                                                tags=[], aliases=[],
                                                requires_privilege=False,
                                                request_schema={}, response_schema={},
                                                implementation='module:Operation')
class OperationRegistry

descriptors_as_dicts(registry) -> list[dict[str, Any]]
```

---

## Notes

* The registry holds operations, not capabilities. The capability is the
  category; the operation is the thing you can run.
* `registry.create(name)` instantiates the operation class. It raises
  `OperationNotFoundError` when the name is unknown, and the exception
  carries the available names — a typo in a script gets a useful answer.
* See also: [the architecture](../../docs/ARCHITECTURE.md#the-registry),
  [core.md](../../core/docs/README.md), [plugins.md](../../plugins/docs/README.md).
