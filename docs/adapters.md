# `netforge.adapters`

The adapter layer: the command line, the REST API, MCP and LlamaIndex.

Four adapters, one contract. Every adapter reads the same registry and
renders it in its own way. None of them reimplements a capability.

| Adapter | Extra | What it exposes |
|---|---|---|
| `cli` | — | the catalogue and the operations |
| `rest` | `rest` | `GET /operations`, `POST /operations/{name}`, … |
| `mcp` | `mcp` | every operation as an MCP tool |
| `llamaindex` | `llamaindex` | every operation as a `FunctionTool` |

---

## The adapter contract

```python
class Adapter(ABC):
    @abstractmethod
    def available(self) -> bool: ...
    @abstractmethod
    def describe(self) -> dict[str, Any]: ...
    def unavailable_reason(self) -> str | None: ...
```

`available()` says whether the adapter is usable in this installation.
`describe()` says what it is and what it can do. `unavailable_reason()`
returns exactly what is missing and how to install it — so the CLI can
answer "install `netforge[rest]`" rather than "no module named
`fastapi`".

**An adapter is never partial.** It exposes the whole catalogue or it is
not available at all. A tool that works for some capabilities and silently
does not work for others is worse than no tool.

The REST adapter needs two packages — `fastapi` to build the application
and `uvicorn` to serve it — so it is available only when *both* are
installed. When either is missing, the reason names every missing package
at once, because they come from the same extra:

```text
the optional dependencies 'fastapi' and 'uvicorn' are required for the
REST adapter. Install it with: pip install 'netforge[rest]'
```

An adapter that could build the application but not serve it would be
partial, and `available()` says so rather than promising something the
adapter cannot deliver.

---

## The CLI

The CLI is built on `argparse` and is always available — standard library
only, no extra.

```bash
netforge list                       # the catalogue, grouped by category
netforge describe discovery.ping    # one operation, in full
netforge categories                 # the capability categories
netforge risk                       # the risk profile of the catalogue
netforge run discovery.ping --request '{"host": "10.0.0.1"}'
netforge serve rest --port 8000     # start another adapter
```

`build_parser()` returns the `argparse.ArgumentParser`, and
`main(argv=None)` runs the command and returns its exit code. `main` is
the console script: `netforge = "netforge.adapters.cli:main"`.

`CliAdapter(registry=None)` is the adapter itself, if you want to embed
the command line in something larger.

---

## The REST adapter

Needs the `rest` extra (`fastapi`, `uvicorn`).

```python
from netforge.adapters import build_app

app = build_app()                    # a FastAPI application
```

`build_app(registry=None, *, max_risk=4)` returns the FastAPI application
over the whole catalogue. `serve_rest` starts it with uvicorn, which is
what `netforge serve rest` calls.

| Route | What it does |
|---|---|
| `GET /health` | is the framework up? |
| `GET /operations` | the catalogue, with the filters |
| `GET /operations/{name}` | one operation, with its schemas |
| `POST /operations/{name}` | run an operation; the body is the request |
| `GET /categories` | the capability categories |
| `GET /risk` | the risk profile |

---

## The MCP adapter

Needs the `mcp` extra.

```python
from netforge.adapters import build_server

server = build_server()              # an MCP server over the registry
```

`build_server(registry=None)` returns the server; `netforge serve mcp`
starts it.

---

## The LlamaIndex adapter

Needs the `llamaindex` extra (`llama-index-core`).

```python
from netforge.adapters import build_tools

tools = build_tools()                # a FunctionTool per operation
```

`build_tools(registry=None)` returns a list of function tools. The tool
signatures are derived from the operation's request model, so the schema
the model publishes is the schema the tool carries.

---

## The public API

```text
class Adapter(ABC)
class AdapterError(Exception)
class CliAdapter          (registry=None)
class LlamaIndexAdapter   (registry=None)
class McpAdapter          (registry=None)
class RestAdapter         (registry=None)

build_app(registry=None, *, max_risk=4) -> Any          a FastAPI application
build_parser() -> argparse.ArgumentParser
build_server(registry=None) -> Any                      an MCP server
build_tools(registry=None) -> list[Any]                 FunctionTool per operation
main(argv=None) -> int                                  the `netforge` command

# in netforge.adapters.base, for anyone writing an adapter
find_missing_dependencies(requirements) -> list[str]     the names that are not installed
```

---

## Notes

* The optional adapters import their extra **lazily**, inside the method
  that needs it. That is why `netforge.adapters` can be imported on a
  machine with no extras at all, and why the adapter can still be
  *listed*.
* `Adapters` never import a capability package. They read the registry,
  and the registry is the only thing they know about.
* `AdapterError` is deliberately *not* a `NetForgeError` — an adapter
  failing is an adapter's problem, not the framework's.
* See also: [the architecture](ARCHITECTURE.md#the-adapters),
  [registry.md](registry.md).
