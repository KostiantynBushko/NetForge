"""The command-line adapter and the other adapters."""

from __future__ import annotations

import importlib.metadata
import json

import pytest

from netforge.adapters import rest
from netforge.adapters.cli import CliAdapter, build_parser, main
from netforge.adapters.llamaindex import LlamaIndexAdapter, tool_parameters
from netforge.adapters.mcp import McpAdapter, tool_description
from netforge.adapters.rest import RestAdapter, serve_rest
from netforge.core.exceptions import DependencyMissingError


def _installed(distribution: str) -> bool:
    """Return whether an optional distribution is installed."""
    try:
        importlib.metadata.distribution(distribution)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


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


class TestTheParametersOnTheCommandLine:
    """The parameters of an operation are given as flags.

    Only the paths that stop before the operation runs are tested here:
    the suite is offline.
    """

    def test_an_unknown_parameter_is_a_usage_error(self, capsys):
        assert main(["run", "discovery.ping", "--hosst", "1.2.3.4"]) == 2
        assert "unknown parameter" in capsys.readouterr().err

    def test_the_refusal_names_the_parameters_there_are(self, capsys):
        assert main(["run", "discovery.ping", "--nope", "1"]) == 2
        assert "host" in capsys.readouterr().err

    def test_a_value_that_does_not_fit_is_a_usage_error(self, capsys):
        assert main(["run", "connectivity.tcp.connect", "--host", "x", "--port", "z"]) == 2
        assert "whole number" in capsys.readouterr().err

    def test_the_help_of_an_operation_lists_its_parameters(self, capsys):
        assert main(["run", "discovery.service.enumerate", "--help"]) == 0
        output = capsys.readouterr().out
        assert "--host" in output
        assert "--ports" in output
        assert "--concurrency" in output

    def test_the_help_of_the_command_says_how_the_parameters_are_given(self, capsys):
        assert main(["run", "--help"]) == 0
        assert "--host 192.168.0.13" in capsys.readouterr().out

    def test_an_unknown_flag_of_another_command_is_a_usage_error(self, capsys):
        assert main(["list", "--nope"]) == 2
        assert "unrecognized arguments" in capsys.readouterr().err

    def test_the_operation_may_be_named_after_the_flags(self, capsys):
        # The risk ceiling refuses the operation before it runs, so the
        # suite stays offline -- and the refusal names the operation,
        # which is what the reordering is for.
        arguments = ["--max-risk", "1", "run", "--host", "10.0.0.1"]
        arguments.append("discovery.service.enumerate")
        assert main(arguments) == 1
        assert "discovery.service.enumerate" in capsys.readouterr().err


class TestAdapterContract:
    def test_the_cli_adapter_is_always_available(self, registry):
        adapter = CliAdapter(registry)
        assert adapter.available() is True
        assert adapter.unavailable_reason() is None

    def test_the_rest_adapter_reports_why_it_is_unavailable(self, registry):
        adapter = RestAdapter(registry)
        assert isinstance(adapter.available(), bool)
        reason = adapter.unavailable_reason()
        if adapter.available():
            assert reason is None
        else:
            assert reason and ("fastapi" in reason or "uvicorn" in reason)

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


class TestRestDependencies:
    """The REST adapter needs two packages, and says so about both.

    They come from the same extra, so a user who installs it should be
    told about the next one in the same message -- not on the next run.
    """

    @staticmethod
    def _missing(name):
        def loader():
            raise DependencyMissingError(name, extra="rest")

        return loader

    def test_every_missing_dependency_is_named(self, registry, monkeypatch):
        monkeypatch.setattr(rest, "_load_fastapi", self._missing("fastapi"))
        monkeypatch.setattr(rest, "_load_uvicorn", self._missing("uvicorn"))

        reason = RestAdapter(registry).unavailable_reason() or ""
        assert "fastapi" in reason
        assert "uvicorn" in reason

    def test_the_adapter_is_not_available_without_uvicorn(self, registry, monkeypatch):
        monkeypatch.setattr(rest, "_load_fastapi", lambda: object())
        monkeypatch.setattr(rest, "_load_uvicorn", self._missing("uvicorn"))

        adapter = RestAdapter(registry)
        assert adapter.available() is False
        assert "uvicorn" in (adapter.unavailable_reason() or "")

    def test_the_adapter_is_not_available_without_fastapi(self, registry, monkeypatch):
        monkeypatch.setattr(rest, "_load_fastapi", self._missing("fastapi"))
        monkeypatch.setattr(rest, "_load_uvicorn", lambda: object())

        adapter = RestAdapter(registry)
        assert adapter.available() is False
        assert "fastapi" in (adapter.unavailable_reason() or "")

    def test_the_adapter_is_available_when_both_are_installed(self, registry, monkeypatch):
        monkeypatch.setattr(rest, "_load_fastapi", lambda: object())
        monkeypatch.setattr(rest, "_load_uvicorn", lambda: object())

        adapter = RestAdapter(registry)
        assert adapter.available() is True
        assert adapter.unavailable_reason() is None

    def test_serving_names_every_missing_dependency(self, registry, monkeypatch):
        monkeypatch.setattr(rest, "_load_fastapi", self._missing("fastapi"))
        monkeypatch.setattr(rest, "_load_uvicorn", self._missing("uvicorn"))

        with pytest.raises(DependencyMissingError) as caught:
            serve_rest(registry)
        message = str(caught.value)
        assert "fastapi" in message
        assert "uvicorn" in message
        assert "netforge[rest]" in message

    def test_the_error_carries_every_dependency(self, registry, monkeypatch):
        monkeypatch.setattr(rest, "_load_fastapi", self._missing("fastapi"))
        monkeypatch.setattr(rest, "_load_uvicorn", self._missing("uvicorn"))

        with pytest.raises(DependencyMissingError) as caught:
            serve_rest(registry)
        assert caught.value.dependencies == ["fastapi", "uvicorn"]


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


class TestTheLlamaIndexTools:
    """Every LlamaIndex tool must run the operation it is named after.

    The builder used to close over a variable of its own loop, so every
    tool it produced ran the *last* operation of the registry.  The tests
    below are the ones that would have caught it.
    """

    @pytest.fixture(autouse=True)
    def _the_extra_is_installed(self):
        if not _installed("llama-index-core"):
            pytest.skip("llama-index-core is not installed")

    @pytest.fixture
    def tools(self, registry):
        from netforge.adapters.llamaindex import build_tools

        return {tool.metadata.name: tool for tool in build_tools(registry)}

    def test_there_is_a_tool_for_every_operation(self, registry, tools):
        assert set(tools) == set(registry.names())

    def test_every_tool_carries_the_schema_of_its_own_operation(self, registry, tools):
        for name, tool in tools.items():
            expected = registry.get_operation(name).request_model
            assert tool.metadata.fn_schema is expected, name

    def test_a_tool_advertises_the_parameters_of_its_operation(self, tools):
        schema = tools["discovery.ping"].metadata.fn_schema.model_json_schema()
        assert "host" in schema["properties"]
        assert "count" in schema["properties"]
        assert schema["required"] == ["host"]

    def test_a_tool_runs_the_operation_it_is_named_after(self, tools):
        result = json.loads(tools["configuration.validate"].fn(content="{}"))
        assert result["operation"] == "configuration.validate"

    def test_two_tools_run_two_different_operations(self, tools):
        first = json.loads(tools["configuration.validate"].fn(content="{}"))
        second = json.loads(
            tools["configuration.diff"].fn(current="{}", candidate="{}")
        )
        assert first["operation"] == "configuration.validate"
        assert second["operation"] == "configuration.diff"


class TestTheMcpTools:
    """The MCP server must build, and every tool must run its own operation.

    The class behind the server was renamed in mcp 2.x, and the tool
    builder used a parameter name the SDK refuses.  The adapter has to
    work with the SDK that is installed, and has to say so when it is
    not usable.
    """

    @pytest.fixture(autouse=True)
    def _the_extra_is_installed(self):
        if not _installed("mcp"):
            pytest.skip("mcp is not installed")

    @pytest.fixture
    def server(self, registry):
        from netforge.adapters.mcp import build_server

        return build_server(registry)

    @staticmethod
    def _the_text(result) -> str:
        """Return the text of the first content block of a tool result."""
        return result.content[0].text

    def test_the_server_builds(self, server):
        assert server is not None

    def test_there_is_a_tool_for_every_operation(self, registry, server):
        import asyncio

        tools = asyncio.run(server.list_tools())
        assert {tool.name for tool in tools} == set(registry.names())

    def test_every_tool_declares_the_parameters_of_its_operation(self, registry, server):
        import asyncio

        tools = asyncio.run(server.list_tools())
        for tool in tools:
            expected = registry.get_operation(tool.name).request_model
            declared = set(tool.input_schema.get("properties", {}))
            assert declared == set(expected.model_fields), tool.name

    def test_a_tool_runs_the_operation_it_is_named_after(self, server):
        import asyncio

        result = asyncio.run(server.call_tool("configuration.validate", {"content": "{}"}))
        assert json.loads(self._the_text(result))["operation"] == "configuration.validate"

    def test_two_tools_run_two_different_operations(self, server):
        import asyncio

        first = asyncio.run(
            server.call_tool("configuration.validate", {"content": "{}"})
        )
        second = asyncio.run(
            server.call_tool("configuration.diff", {"current": "{}", "candidate": "{}"})
        )
        assert json.loads(self._the_text(first))["operation"] == "configuration.validate"
        assert json.loads(self._the_text(second))["operation"] == "configuration.diff"

    def test_the_adapter_is_not_available_without_the_server_class(self, registry, monkeypatch):
        from netforge.adapters import mcp

        def missing():
            raise DependencyMissingError("mcp", extra="mcp")

        monkeypatch.setattr(mcp, "_load_mcp", missing)

        adapter = McpAdapter(registry)
        assert adapter.available() is False
        assert "mcp" in (adapter.unavailable_reason() or "")

    def test_an_unusable_version_of_mcp_is_reported_honestly(self, registry, monkeypatch):
        from netforge.adapters import mcp
        from netforge.adapters.base import AdapterError

        def unusable():
            raise AdapterError("the installed version of mcp has neither MCPServer nor FastMCP")

        monkeypatch.setattr(mcp, "_load_mcp", unusable)

        adapter = McpAdapter(registry)
        assert adapter.available() is False
        reason = adapter.unavailable_reason() or ""
        assert "mcp" in reason
        assert "version" in reason
