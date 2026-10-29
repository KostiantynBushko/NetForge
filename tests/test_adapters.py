"""The command-line adapter and the other adapters."""

from __future__ import annotations

import json

import pytest

from netforge.adapters.base import Adapter
from netforge.adapters.cli import CliAdapter, build_parser, main
from netforge.adapters.llamaindex import LlamaIndexAdapter, tool_parameters
from netforge.adapters.mcp import McpAdapter, tool_description
from netforge.adapters.rest import RestAdapter


class TestCli:
    def test_the_parser_is_built(self):
        parser = build_parser()
        assert parser.prog == "netforge"

    def test_no_command_prints_the_help(self, capsys):
        assert main([]) == 2
        assert "usage: netforge" in capsys.readouterr().out

    def test_the_list_command_prints_the_catalogue(self, capsys):
        assert main(["list"]) == 0
        output = capsys.readouterr().out
        assert "discovery.ping" in output
        assert "operation(s)" in output

    def test_the_list_command_can_emit_json(self, capsys):
        assert main(["list", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, list)
        assert any(item["name"] == "discovery.ping" for item in payload)

    def test_the_list_command_filters_by_category(self, capsys):
        assert main(["list", "--category", "security", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload
        assert all(item["category"] == "security" for item in payload)

    def test_the_describe_command_prints_the_schema(self, capsys):
        assert main(["describe", "discovery.ping"]) == 0
        output = capsys.readouterr().out
        assert "discovery.ping" in output
        assert "request schema" in output

    def test_the_describe_command_fails_on_an_unknown_operation(self, capsys):
        assert main(["describe", "does.not.exist"]) == 1
        assert "OperationNotFoundError" in capsys.readouterr().err

    def test_the_categories_command_lists_them(self, capsys):
        assert main(["categories"]) == 0
        output = capsys.readouterr().out
        assert "Discovery" in output
        assert "Security" in output

    def test_the_risk_command_prints_the_profile(self, capsys):
        assert main(["risk", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert sum(payload.values()) > 0

    def test_an_invalid_request_is_a_usage_error(self, capsys):
        assert main(["run", "discovery.ping", "--request", "{not json"]) == 2
        assert "not valid JSON" in capsys.readouterr().err

    def test_a_request_that_is_not_an_object_is_a_usage_error(self, capsys):
        assert main(["run", "discovery.ping", "--request", "[1]"]) == 2
        assert "must be a JSON object" in capsys.readouterr().err

    def test_an_unknown_max_risk_is_a_usage_error(self, capsys):
        assert main(["--max-risk", "catastrophic", "list"]) == 2
        assert "unknown risk level" in capsys.readouterr().err

    def test_the_risk_ceiling_filters_the_catalogue(self, capsys):
        assert main(["--max-risk", "1", "list", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert all(item["risk_level"] <= 1 for item in payload)

    def test_an_operation_above_the_ceiling_is_refused(self, capsys):
        assert main(["--max-risk", "1", "run", "configuration.restore", "--request", "{}"]) == 1
        assert "RiskPolicyError" in capsys.readouterr().err


class TestAdapterContract:
    def test_the_cli_adapter_is_always_available(self, registry):
        adapter = CliAdapter(registry)
        assert adapter.available() is True
        assert adapter.unavailable_reason() is None

    def test_the_rest_adapter_reports_why_it_is_unavailable(self, registry):
        adapter = RestAdapter(registry)
        assert isinstance(adapter.available(), bool)
        if not adapter.available():
            assert "fastapi" in (adapter.unavailable_reason() or "")

    def test_the_mcp_adapter_reports_why_it_is_unavailable(self, registry):
        adapter = McpAdapter(registry)
        assert isinstance(adapter.available(), bool)
        if not adapter.available():
            assert "mcp" in (adapter.unavailable_reason() or "")

    def test_the_llamaindex_adapter_reports_why_it_is_unavailable(self, registry):
        adapter = LlamaIndexAdapter(registry)
        assert isinstance(adapter.available(), bool)

    def test_every_adapter_describes_itself(self, registry):
        from netforge.adapters.cli import CliAdapter
        from netforge.adapters.llamaindex import LlamaIndexAdapter
        from netforge.adapters.mcp import McpAdapter
        from netforge.adapters.rest import RestAdapter

        for adapter in (
            CliAdapter(registry),
            RestAdapter(registry),
            McpAdapter(registry),
            LlamaIndexAdapter(registry),
        ):
            described = adapter.describe()
            assert described["name"] == adapter.name
            assert "available" in described


class TestToolParameters:
    def test_the_request_schema_becomes_the_tool_parameters(self, registry):
        descriptor = registry.get("discovery.ping")
        parameters = tool_parameters(descriptor)
        assert "host" in parameters
        assert parameters["host"]["type"] == "string"
        assert parameters["host"]["required"] is True

    def test_the_tool_description_names_the_risk_level(self, registry):
        descriptor = registry.get("configuration.restore")
        description = tool_description(descriptor)
        assert "Risk level" in description
        assert "System Modification" in description
