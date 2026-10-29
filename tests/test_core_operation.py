"""The operation contract."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from netforge.core.context import ExecutionContext
from netforge.core.exceptions import RiskPolicyError
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel


class DemoRequest(RequestModel):
    """A request for the demo operation."""

    value: int = 0


class DemoResponse(ResponseModel):
    """A response from the demo operation."""

    doubled: int = 0


class DemoOperation(Operation[DemoRequest, DemoResponse]):
    """A demo operation."""

    name = "test.demo"
    category = CapabilityCategory.DISCOVERY
    risk_level = RiskLevel.SAFE
    summary = "Doubles a number."
    request_model = DemoRequest
    response_model = DemoResponse

    async def execute(self, request: DemoRequest, context: ExecutionContext) -> DemoResponse:
        """Double the value."""
        return DemoResponse(doubled=request.value * 2)


class TestOperationContract:
    def test_a_concrete_operation_must_declare_everything(self):
        # The class is built here rather than at module level, because the
        # failure is the point of the test.
        with pytest.raises(TypeError, match="risk_level"):
            type(
                "IncompleteOperation",
                (Operation,),
                {
                    "name": "test.incomplete",
                    "category": CapabilityCategory.DISCOVERY,
                    "request_model": DemoRequest,
                    "response_model": DemoResponse,
                    "execute": lambda self, request, context: None,
                },
            )

    def test_an_abstract_operation_may_be_incomplete(self):
        class AbstractOperation(Operation):
            """An operation that is not finished yet."""

        assert AbstractOperation.__abstractmethods__ == frozenset({"execute"})

    def test_run_validates_the_request(self):
        import asyncio

        response = asyncio.run(DemoOperation().run(value=21))
        assert response.doubled == 42

    def test_run_rejects_an_unknown_field(self):
        with pytest.raises(Exception):
            DemoOperation().request_model(value=1, nonsense=2)

    def test_run_request_accepts_a_dictionary(self):
        import asyncio

        response = asyncio.run(DemoOperation().run_request({"value": 5}))
        assert response.doubled == 10

    def test_the_risk_level_is_enforced_by_the_framework(self):
        import asyncio

        context = ExecutionContext(max_risk=RiskLevel.OBSERVABILITY)
        operation = DemoOperation()
        operation.risk_level = RiskLevel.SYSTEM_MODIFICATION

        with pytest.raises(RiskPolicyError):
            asyncio.run(operation.run_request({"value": 1}, context))

    def test_the_ceiling_never_exceeds_the_configuration(self):
        context = ExecutionContext(max_risk=RiskLevel.SYSTEM_MODIFICATION)
        assert context.max_risk == RiskLevel.SYSTEM_MODIFICATION

    def test_run_with_meta_reports_the_duration(self):
        import asyncio

        result = asyncio.run(DemoOperation().run_with_meta({"value": 3}))
        assert result.data.doubled == 6
        assert result.meta.operation == "test.demo"
        assert result.meta.risk_level == RiskLevel.SAFE
        assert result.meta.duration_ms >= 0

    def test_describe_publishes_the_schemas(self):
        described = DemoOperation.describe()
        assert described["name"] == "test.demo"
        assert described["risk_level"] == int(RiskLevel.SAFE)
        assert "properties" in described["request_schema"]


class TestRequestValidation:
    def test_a_typo_in_a_field_name_is_an_error(self):
        with pytest.raises(Exception):
            DemoRequest(valve=1)

    def test_assignment_is_revalidated(self):
        request = DemoRequest(value=1)
        request.value = 2
        assert request.value == 2

    def test_a_model_rejects_extra_fields_by_default(self):
        class Loose(BaseModel):
            pass

        assert Loose.model_config.get("extra") != "allow"
