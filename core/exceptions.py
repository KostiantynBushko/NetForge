"""The exception hierarchy of NetForge.

Every error NetForge raises on purpose derives from :class:`NetForgeError`.
Adapters catch that one class and report it; the detail is in the message.

The hierarchy is split by *who* can fix the problem:

* :class:`ConfigurationError` -- the operator gave NetForge something it
  cannot work with.
* :class:`OperationNotFoundError` -- the name does not exist.
* :class:`RiskPolicyError` -- the operation exists but is above the ceiling
  the operator allowed.  This one is deliberately its own class: an agent
  that is refused a level-4 operation needs to be able to tell "that does
  not exist" from "that exists and I am not allowed to run it".
* :class:`DependencyMissingError` -- an optional dependency is not
  installed.  The message carries the extra that installs it.
* :class:`OperationExecutionError` -- the operation ran and failed.
"""

from __future__ import annotations

from collections.abc import Iterable

__all__ = [
    "ConfigurationError",
    "DependencyMissingError",
    "NetForgeError",
    "OperationExecutionError",
    "OperationNotFoundError",
    "PluginError",
    "RiskPolicyError",
    "TimeoutError",
]


class NetForgeError(Exception):
    """Base class for every error NetForge raises deliberately."""


class ConfigurationError(NetForgeError):
    """The framework was configured with something it cannot use."""


class OperationNotFoundError(NetForgeError):
    """No operation is registered under the requested name."""

    def __init__(self, name: str, available: list[str] | None = None) -> None:
        self.name = name
        self.available = available or []
        message = f"no operation named {name!r}"
        if self.available:
            close = [n for n in self.available if name[:2].lower() in n.lower()][:5]
            hint = f"; did you mean: {', '.join(close)}?" if close else ""
            message = f"{message}. Registered operations: {len(self.available)}{hint}"
        super().__init__(message)


class RiskPolicyError(NetForgeError):
    """The operation is above the risk ceiling the caller allowed."""

    def __init__(self, operation: str, risk_level: object, ceiling: object) -> None:
        self.operation = operation
        self.risk_level = risk_level
        self.ceiling = ceiling
        super().__init__(
            f"operation {operation!r} is declared at risk level {risk_level} "
            f"({getattr(risk_level, 'label', risk_level)}), which is above the "
            f"permitted ceiling {ceiling} ({getattr(ceiling, 'label', ceiling)})"
        )


class DependencyMissingError(NetForgeError):
    """An optional dependency required by this capability is not installed.

    More than one dependency may be named, when a single extra provides
    several of them.  Reporting them together matters: a user who is told
    about one dependency at a time has to run the command again after each
    installation, to be told about the next one.
    """

    def __init__(
        self,
        dependency: str | Iterable[str],
        extra: str | None = None,
        feature: str = "",
    ) -> None:
        names = [dependency] if isinstance(dependency, str) else list(dependency)
        if not names:
            raise ValueError("at least one dependency must be named")
        #: Every dependency that is missing.
        self.dependencies = names
        #: The missing dependencies, as one string.
        self.dependency = names[0] if len(names) == 1 else " and ".join(names)
        self.extra = extra
        self.feature = feature
        install = f"pip install 'netforge[{extra}]'" if extra else f"pip install {names[0]}"
        if len(names) == 1:
            subject = (
                f"the optional dependency {names[0]!r} is required for {feature}"
                if feature
                else f"the optional dependency {names[0]!r} is required here"
            )
        else:
            listed = " and ".join(repr(name) for name in names)
            subject = (
                f"the optional dependencies {listed} are required for {feature}"
                if feature
                else f"the optional dependencies {listed} are required here"
            )
        super().__init__(f"{subject}. Install it with: {install}")


class OperationExecutionError(NetForgeError):
    """An operation was invoked and failed."""


class PluginError(NetForgeError):
    """A plugin could not be loaded."""


class TimeoutError(NetForgeError):  # noqa: A001 - deliberate domain name
    """An operation exceeded its time budget."""
