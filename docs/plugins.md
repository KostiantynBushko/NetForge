# `netforge.plugins`

A plugin adds operations to NetForge. It is discovered through the
`netforge.plugins` entry point group or through a directory, and it is
loaded without the risk of taking the framework down.

---

## Writing a plugin

A plugin is a class with a name, a version and a list of operations.

```python
from netforge.plugins import Plugin
from netforge.core.operation import Operation


class MyPlugin(Plugin):
    name = "my-plugin"
    version = "1.0.0"

    def operations(self) -> list[type[Operation]]:
        return [MyOperation]
```

The operations are ordinary `Operation` subclasses, so a plugin gets the
whole framework: the risk model, the typed models, the registry and every
adapter, for free.

---

## Publishing a plugin

Declare the entry point in your package's `pyproject.toml`:

```toml
[project.entry-points."netforge.plugins"]
my-plugin = "my_package.plugin:MyPlugin"
```

`ENTRY_POINT_GROUP` is exported as `"netforge.plugins"`, so a packaging
tool can use the constant instead of the literal string.

---

## Loading plugins

```python
from netforge.plugins import PluginManager, discover_plugins

manager = discover_plugins()                    # entry points only
manager = discover_plugins(directories=["/opt/netforge/plugins"])
```

`discover_plugins(registry=None, *, directories=())` loads every plugin it
can find, registers their operations into the registry, and returns the
`PluginManager`.

`PluginManager(registry=None)` is the manager itself, with
`load_entry_points(group=ENTRY_POINT_GROUP)` and `load_directory(path)` as
its two loaders.

---

## Failures are collected, not raised

Every loader collects its failures instead of raising them. A plugin that
cannot be imported is reported in `manager.failures` and skipped.

That is a deliberate choice: a broken third-party plugin must not be able
to stop an operator from running `ping`.

```python
manager = discover_plugins()
for failure in manager.failures:
    print(failure)
```

---

## The public API

```text
class Plugin                                    base class of every plugin
class PluginError(NetForgeError)                a plugin could not be loaded
class PluginManager                             (registry=None)

ENTRY_POINT_GROUP = "netforge.plugins"
discover_plugins(registry=None, *, directories=()) -> PluginManager
```

---

## Notes

* A plugin may declare several operations; they are registered under their
  own names, in the ordinary namespace.
* The entry point group is separate from the operation names — a plugin
  named `my-plugin` can publish `my.check` and `my.report` without any
  prefix collision.
* `PluginError` is a `NetForgeError`, so it is caught by the same `except`
  clause as everything else the framework raises.
* See also: [the architecture](ARCHITECTURE.md#the-plugin-system),
  [registry.md](registry.md), [core.md](core.md).
