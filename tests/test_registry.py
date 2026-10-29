"""The operation registry."""

from __future__ import annotations

import pytest

from netforge.core.exceptions import OperationNotFoundError
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel
from netforge.registry.registry import OperationRegistry


class _Request(RequestModel):
    """A request for the generated operations."""

    value: int = 0


class _Response(ResponseModel):
    """A response from the generated operations."""

    value: int = 0


def _make(op_name: str, op_category: CapabilityCategory, op_risk: RiskLevel):
    """Build an operation class with the given identity.

    The identity has to be declared *in the class body*: the framework
    checks it when the class is created, so an operation cannot be given a
    name after the fact.
    """

    class _Operation(Operation):
        """A generated operation."""

        name = op_name
        category = op_category
        risk_level = op_risk
        request_model = _Request
        response_model = _Response

        async def execute(self, request, context):  # pragma: no cover - never run
            raise NotImplementedError

    return _Operation


class TestRegistration:
    def test_a_built_in_operation_is_registered(self, registry):
        assert "discovery.ping" in registry
        assert len(registry) >= 25

    def test_an_unknown_name_raises_and_lists_what_there_is(self, registry):
        with pytest.raises(OperationNotFoundError) as info:
            registry.get("does.not.exist")
        assert "Registered operations" in str(info.value)

    def test_a_name_cannot_be_registered_twice(self, registry):
        clash = _make("discovery.ping", CapabilityCategory.DISCOVERY, RiskLevel.SAFE)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(clash)

    def test_registering_the_same_class_twice_is_harmless(self, registry):
        operation = registry.get_operation("discovery.ping")
        registry.register(operation)
        assert registry.get("discovery.ping").name == "discovery.ping"

    def test_an_alias_resolves_to_the_canonical_name(self, registry):
        operation = _make("test.aliased", CapabilityCategory.DISCOVERY, RiskLevel.SAFE)
        registry.register(operation, aliases=["test.alias"])
        assert registry.resolve("test.alias") == "test.aliased"
        assert registry.get("test.alias").name == "test.aliased"
        assert "test.alias" in registry

    def test_unregister_removes_the_operation_and_its_aliases(self, registry):
        operation = _make("test.removable", CapabilityCategory.DISCOVERY, RiskLevel.SAFE)
        registry.register(operation, aliases=["test.removable.alias"])
        assert registry.unregister("test.removable.alias") is True
        assert "test.removable" not in registry
        assert "test.removable.alias" not in registry


class TestFiltering:
    def test_the_catalogue_is_sorted_by_name(self, registry):
        names = [descriptor.name for descriptor in registry]
        assert names == sorted(names)

    def test_filtering_by_category(self, registry):
        descriptors = registry.list(category=CapabilityCategory.SECURITY)
        assert descriptors
        assert all(d.category == CapabilityCategory.SECURITY for d in descriptors)

    def test_filtering_by_risk_ceiling(self, registry):
        descriptors = registry.list(max_risk=RiskLevel.SAFE)
        assert descriptors
        assert all(d.risk_level <= RiskLevel.SAFE for d in descriptors)

    def test_filtering_by_tag(self, registry):
        descriptors = registry.list(tag="dns")
        assert descriptors
        assert all("dns" in d.tags for d in descriptors)

    def test_filtering_by_free_text(self, registry):
        descriptors = registry.list(query="dns")
        assert descriptors
        assert any("dns" in d.name for d in descriptors)

    def test_every_built_in_operation_declares_a_risk_level(self, registry):
        for descriptor in registry:
            assert isinstance(descriptor.risk_level, RiskLevel)

    def test_every_built_in_operation_has_a_summary(self, registry):
        for descriptor in registry:
            assert descriptor.summary, f"{descriptor.name} has no summary"

    def test_the_risk_profile_counts_every_operation(self, registry):
        profile = registry.risk_profile()
        assert sum(profile.values()) == len(registry)

    def test_the_categories_cover_every_operation(self, registry):
        grouped = registry.categories()
        assert sum(len(names) for names in grouped.values()) == len(registry)


class TestDescriptors:
    def test_a_descriptor_publishes_the_request_schema(self, registry):
        descriptor = registry.get("discovery.ping")
        assert descriptor.request_schema["type"] == "object"
        assert "host" in descriptor.request_schema["properties"]

    def test_a_descriptor_names_its_implementation(self, registry):
        descriptor = registry.get("discovery.ping")
        assert descriptor.implementation.startswith("netforge.discovery.ping:")
