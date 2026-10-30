# `netforge.configuration`

Reading a configuration, checking it, comparing it with a candidate and
writing it back.

The operations are split by risk: the first three are read-only, the last
one changes the device and is declared at the system modification level.

---

## Operations

<!-- generated:operations -->
| Operation | Risk | What it does |
|---|---|---|
| [`configuration.backup`](backup.md) | Safe | Read a configuration file off a device over SSH. |
| [`configuration.diff`](diff.md) | Safe | Compare two configuration texts and report the difference. |
| [`configuration.restore`](restore.md) | System Modification | Write a configuration file onto a device over SSH. |
| [`configuration.validate`](validate.md) | Safe | Check a configuration text for the problems that break a device. |
<!-- /generated:operations -->

`configuration.restore` is the only operation in the whole catalogue that
writes to a remote device, and it sits at the top of the risk model for
that reason.

---

## Validation

`validate_configuration(text)` returns a list of `ValidationIssue`. Each
issue has a `severity`, a `message` and a `line` when the problem is
attached to one.

```python
from netforge.configuration import validate_configuration

for issue in validate_configuration(text):
    print(issue.severity, issue.line, issue.message)
```

It is a pure function over the configuration text, so it can be checked
against a captured file without a device.

---

## Diffing

`diff_configurations(before, after, *, name="configuration")` returns a
unified diff between two configuration texts, as a list of lines.

```python
from netforge.configuration import diff_configurations

print("\n".join(diff_configurations(old, new, name="running-config")))
```

---

## Using it

```python
backup = registry.create("configuration.backup")
current = await backup.run(host="10.0.0.1", path="/etc/network/interfaces")

diff = registry.create("configuration.diff")
report = await diff.run(before=current.text, after=candidate)
```

---

## The public API

<!-- generated:public-api -->
```text
class ConfigurationBackupOperation()
class ConfigurationDiffOperation()
class ConfigurationRestoreOperation()
class ConfigurationValidateOperation()
class ValidationIssue(severity: str, message: str, line: int | None = None)
def diff_configurations(before: str, after: str, *, name: str = 'configuration') -> list[str]
def validate_configuration(text: str) -> list[ValidationIssue]
```
<!-- /generated:public-api -->

---

## Notes

* The SSH operations need the `ssh` extra (`asyncssh`). Without it they
  report that the dependency is missing, rather than failing to import.
* `configuration.restore` writes a file over SSH. It is the operation the
  risk ceiling exists to protect: run with a lower `--max-risk` and it is
  refused before the payload is even validated.
* The validation rules cover the problems that break a device — a missing
  interface, an address that is not on the subnet, a duplicate route —
  not the whole grammar of every vendor's configuration language.
* See also: [the architecture](../../docs/ARCHITECTURE.md),
  [connectivity.md](../../connectivity/docs/README.md), [dns.md](../../dns/docs/README.md).
