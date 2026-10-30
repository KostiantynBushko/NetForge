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
    """An optional dependency required by this capability is not installed."""

    def __init__(self, dependency: str, extra: str | None = None, feature: str = "") -> None:
        self.dependency = dependency
        self.extra = extra
        self.feature = feature
        install = f"pip install 'netforge[{extra}]'" if extra else f"pip install {dependency}"
        subject = (
            f"the optional dependency {dependency!r} is required for {feature}"
            if feature
            else f"the optional dependency {dependency!r} is required here"
        )
        super().__init__(f"{subject}. Install it with: {install}")


class OperationExecutionError(NetForgeError):
    """An operation was invoked and failed."""


class PluginError(NetForgeError):
    """A plugin could not be loaded."""


class TimeoutError(NetForgeError):  # noqa: A001 - deliberate domain name
    """An operation exceeded its time budget."""
