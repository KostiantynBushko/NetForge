"""The native acceleration layer.

The specification allows a performance-critical module to be reimplemented
in Rust or C++ while the public API stays identical.  This module is the
seam where that happens.

The rule is that the *caller* never learns which implementation served an
operation.  A native implementation registers itself under the name of the
operation it accelerates, and the registry resolves it transparently.

Nothing here is enabled by default: an operation is only served natively if
a native implementation has been registered for it *and* the context allows
native execution (:attr:`NetForgeConfig.allow_native`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from netforge.core.exceptions import ConfigurationError
from netforge.core.logging import get_logger

__all__ = ["NativeImplementation", "NativeRegistry", "native_registry"]

_logger = get_logger("core.native")


@dataclass(frozen=True, slots=True)
class NativeImplementation:
    """A native implementation of one operation."""

    operation: str
    language: str
    entrypoint: Callable[..., Any]
    version: str = "unknown"

    def describe(self) -> dict[str, str]:
        """Return a JSON-serialisable description."""
        return {
            "operation": self.operation,
            "language": self.language,
            "version": self.version,
        }


class NativeRegistry:
    """Keeps track of the native implementations that are available."""

    def __init__(self) -> None:
        self._implementations: dict[str, NativeImplementation] = {}

    def register(self, implementation: NativeImplementation) -> None:
        """Register a native implementation for an operation."""
        existing = self._implementations.get(implementation.operation)
        if existing is not None:
            _logger.info(
                "native implementation for %s replaced (%s -> %s)",
                implementation.operation,
                existing.language,
                implementation.language,
            )
        self._implementations[implementation.operation] = implementation

    def get(self, operation: str) -> NativeImplementation | None:
        """Return the native implementation for ``operation``, if any."""
        return self._implementations.get(operation)

    def has(self, operation: str) -> bool:
        """Return ``True`` when a native implementation is registered."""
        return operation in self._implementations

    def list(self) -> list[NativeImplementation]:
        """Return every registered implementation, sorted by operation name."""
        return sorted(self._implementations.values(), key=lambda impl: impl.operation)

    def clear(self) -> None:
        """Remove every registered implementation."""
        self._implementations.clear()

    def __len__(self) -> int:
        return len(self._implementations)

    def __contains__(self, operation: object) -> bool:
        return isinstance(operation, str) and operation in self._implementations


#: The process-wide native registry.
native_registry = NativeRegistry()


def load_native_module(module_path: str) -> None:
    """Import ``module_path`` and register whatever it exposes.

    The module is expected to expose a ``register(registry)`` function, or
    a ``NATIVE_IMPLEMENTATIONS`` iterable of :class:`NativeImplementation`.
    """
    import importlib

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ConfigurationError(f"native module {module_path!r} is not available: {exc}") from exc

    registrar = getattr(module, "register", None)
    if callable(registrar):
        registrar(native_registry)
        return

    implementations = getattr(module, "NATIVE_IMPLEMENTATIONS", None)
    if implementations:
        for implementation in implementations:
            native_registry.register(implementation)
        return

    raise ConfigurationError(
        f"native module {module_path!r} exposes neither register() nor NATIVE_IMPLEMENTATIONS"
    )
