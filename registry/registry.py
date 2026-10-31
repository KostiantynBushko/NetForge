"""The operation registry.

The registry is the single catalogue of everything NetForge can do.  It is
what makes the specification's promise possible -- *"a capability implemented
once in NetForge should be automatically available through any supported
adapter"* -- because every adapter reads from the registry and from nowhere
else.

The registry is deliberately boring: a mapping from a name to a descriptor,
plus the class behind it.  It is created empty, filled by
:func:`netforge.core.bootstrap.load_builtin_operations` and by plugins, and
then it is read.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable, Iterator
from types import ModuleType
from typing import Any

from netforge.core.exceptions import OperationNotFoundError
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel
from netforge.registry.descriptor import OperationDescriptor

__all__ = ["OperationRegistry"]

_logger = get_logger("registry")


class OperationRegistry:
    """A catalogue of operations, addressable by name."""

    def __init__(self) -> None:
        self._descriptors: dict[str, OperationDescriptor] = {}
        self._classes: dict[str, type[Operation]] = {}
        self._aliases: dict[str, str] = {}

    # -- registration -------------------------------------------------------

    def register(
        self,
        operation_cls: type[Operation],
        *,
        name: str | None = None,
        aliases: Iterable[str] = (),
    ) -> OperationDescriptor:
        """Register an operation class and return its descriptor.

        The name defaults to the class's ``name`` attribute.  An alias is an
        additional name the operation answers to; it never replaces the
        canonical name.
        """
        if not inspect.isclass(operation_cls) or not issubclass(operation_cls, Operation):
            raise TypeError(f"{operation_cls!r} is not an Operation subclass")

        canonical = name or operation_cls.name
        if not canonical:
            raise ValueError(f"{operation_cls.__name__} has no name")

        existing = self._classes.get(canonical)
        if existing is not None and existing is not operation_cls:
            raise ValueError(
                f"operation name {canonical!r} is already registered to "
                f"{existing.__module__}.{existing.__qualname__}"
            )

        descriptor = OperationDescriptor(
            name=canonical,
            category=operation_cls.category,
            risk_level=operation_cls.risk_level,
            summary=operation_cls.summary,
            description=operation_cls.description,
            tags=sorted(operation_cls.tags),
            aliases=list(aliases),
            requires_privilege=operation_cls.requires_privilege,
            request_schema=operation_cls.request_model.model_json_schema(),
            response_schema=operation_cls.response_model.model_json_schema(),
            implementation=f"{operation_cls.__module__}:{operation_cls.__qualname__}",
        )

        self._descriptors[canonical] = descriptor
        self._classes[canonical] = operation_cls
        for alias in aliases:
            self._aliases[alias] = canonical

        _logger.debug("registered operation %s (%s)", canonical, descriptor.risk_level.label)
        return descriptor

    def register_module(self, module: ModuleType) -> list[OperationDescriptor]:
        """Register every operation defined in ``module``.

        Only classes *defined in that module* are registered, so importing a
        module that merely imports an operation does not register it twice.
        """
        registered: list[OperationDescriptor] = []
        for _name, obj in vars(module).items():
            if not inspect.isclass(obj):
                continue
            if not issubclass(obj, Operation) or obj is Operation:
                continue
            if obj.__module__ != module.__name__:
                continue
            registered.append(self.register(obj))
        return registered

    def unregister(self, name: str) -> bool:
        """Remove an operation from the registry.  Returns ``True`` if it was there."""
        canonical = self._aliases.get(name, name)
        removed = canonical in self._descriptors
        self._descriptors.pop(canonical, None)
        self._classes.pop(canonical, None)
        for alias, target in list(self._aliases.items()):
            if target == canonical:
                del self._aliases[alias]
        return removed

    # -- lookup -------------------------------------------------------------

    def get(self, name: str) -> OperationDescriptor:
        """Return the descriptor of ``name``.

        Aliases resolve to their canonical operation.  An unknown name
        raises :class:`OperationNotFoundError`, which lists what *is*
        registered.
        """
        canonical = self._aliases.get(name, name)
        try:
            return self._descriptors[canonical]
        except KeyError:
            raise OperationNotFoundError(name, sorted(self._descriptors)) from None

    def get_operation(self, name: str) -> type[Operation]:
        """Return the implementation class of ``name``."""
        canonical = self._aliases.get(name, name)
        try:
            return self._classes[canonical]
        except KeyError:
            raise OperationNotFoundError(name, sorted(self._descriptors)) from None

    def create(self, name: str) -> Operation:
        """Instantiate the operation registered under ``name``."""
        return self.get_operation(name)()

    def resolve(self, name: str) -> str:
        """Return the canonical name for ``name``, or ``name`` itself."""
        return self._aliases.get(name, name)

    # -- listing ------------------------------------------------------------

    def list(
        self,
        *,
        category: CapabilityCategory | str | None = None,
        max_risk: RiskLevel | int | None = None,
        tag: str | None = None,
        query: str | None = None,
    ) -> list[OperationDescriptor]:
        """Return the descriptors that match the given filters.

        The result is sorted by name, so every adapter renders the same
        catalogue in the same order.
        """
        if category is not None:
            category = CapabilityCategory.parse(category)
        if max_risk is not None:
            max_risk = RiskLevel.parse(max_risk)

        selected: list[OperationDescriptor] = []
        for descriptor in self._descriptors.values():
            if category is not None and descriptor.category != category:
                continue
            if max_risk is not None and descriptor.risk_level > max_risk:
                continue
            if tag is not None and tag not in descriptor.tags:
                continue
            if query is not None and not _matches(descriptor, query):
                continue
            selected.append(descriptor)
        return sorted(selected, key=lambda d: d.name)

    def names(self) -> list[str]:
        """Return every registered operation name, sorted."""
        return sorted(self._descriptors)

    def categories(self) -> dict[str, list[str]]:
        """Return the operation names grouped by category."""
        grouped: dict[str, list[str]] = {category.value: [] for category in CapabilityCategory}
        for descriptor in sorted(self._descriptors.values(), key=lambda d: d.name):
            grouped[descriptor.category.value].append(descriptor.name)
        return grouped

    def risk_summary(self) -> dict[str, list[str]]:
        """Return the operation names grouped by risk level."""
        grouped: dict[str, list[str]] = {level.label: [] for level in RiskLevel}
        for descriptor in sorted(self._descriptors.values(), key=lambda d: d.name):
            grouped[descriptor.risk_level.label].append(descriptor.name)
        return grouped

    def risk_profile(self) -> dict[str, int]:
        """Return how many operations sit at each risk level."""
        counts = {level.label: 0 for level in RiskLevel}
        for descriptor in self._descriptors.values():
            counts[descriptor.risk_level.label] += 1
        return counts

    # -- container protocol -------------------------------------------------

    def __contains__(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        return name in self._descriptors or name in self._aliases

    def __len__(self) -> int:
        return len(self._descriptors)

    def __iter__(self) -> Iterator[OperationDescriptor]:
        return iter(sorted(self._descriptors.values(), key=lambda d: d.name))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<OperationRegistry {len(self)} operations>"


def _matches(descriptor: OperationDescriptor, query: str) -> bool:
    needle = query.strip().lower()
    if not needle:
        return True
    haystacks = (
        descriptor.name,
        descriptor.summary,
        descriptor.description,
        " ".join(descriptor.tags),
        descriptor.category.value,
    )
    return any(needle in text.lower() for text in haystacks)


def descriptors_as_dicts(registry: OperationRegistry) -> list[dict[str, Any]]:
    """Return the registry's descriptors as plain dictionaries."""
    return [descriptor.model_dump(mode="json") for descriptor in registry]
