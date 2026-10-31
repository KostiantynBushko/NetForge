"""The agent adapters, and the promise that they all keep.

NetForge is meant to be used by an agent framework.  This file is where
that promise is checked: every adapter must expose the same operations,
declare the same parameters, and return the same response.  A framework
that is not on the list is a framework nobody has tried.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest

from netforge.registry.registry import OperationRegistry


def _installed(distribution: str) -> bool:
    """Return whether an optional distribution is installed."""
    try:
        importlib.metadata.distribution(distribution)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def _without_the_timing(response: dict[str, Any]) -> dict[str, Any]:
    """Return the response without the field that differs every time."""
    return {key: value for key, value in response.items() if key != "duration_ms"}


@dataclass
class Framework:
    """One framework, and how to look at the tools it exposes.

    Every adapter reaches the operations in its own way: LlamaIndex wraps
    a function, Pydantic AI wants a model, LangChain wants an
    ``args_schema``, MCP speaks JSON-RPC.  The three functions below are
    the whole of the difference, and they are what the tests below use.
    """

    name: str
    tools: dict[str, Any]
    schema_of: Callable[[Any], dict[str, Any]]
    invoke: Callable[[str, dict[str, Any]], Awaitable[Any]]


def _llamaindex(registry: OperationRegistry) -> Framework:
    from netforge.adapters.llamaindex import build_tools

    tools = {tool.metadata.name: tool for tool in build_tools(registry)}

    async def invoke(name: str, arguments: dict[str, Any]) -> Any:
        return json.loads(tools[name].fn(**arguments))

    return Framework(
        name="llamaindex",
        tools=tools,
        schema_of=lambda tool: tool.metadata.fn_schema.model_json_schema(),
        invoke=invoke,
    )


def _pydantic_ai(registry: OperationRegistry) -> Framework:
    from netforge.adapters.pydantic_ai import build_tools

    tools = {tool.name: tool for tool in build_tools(registry)}

    async def invoke(name: str, arguments: dict[str, Any]) -> Any:
        tool = tools[name]
        request_model = tool.function.__annotations__["request"]
        return json.loads(await tool.function(request=request_model(**arguments)))

    return Framework(
        name="pydantic-ai",
        tools=tools,
        schema_of=lambda tool: tool.function_schema.json_schema,
        invoke=invoke,
    )


def _langchain(registry: OperationRegistry) -> Framework:
    from netforge.adapters.langchain import build_tools

    tools = {tool.name: tool for tool in build_tools(registry)}

    async def invoke(name: str, arguments: dict[str, Any]) -> Any:
        return json.loads(await tools[name].ainvoke(arguments))

    return Framework(
        name="langchain",
        tools=tools,
        schema_of=lambda tool: tool.args_schema.model_json_schema(),
        invoke=invoke,
    )


def _mcp(registry: OperationRegistry) -> Framework:
    from netforge.adapters.mcp import build_server

    server = build_server(registry)
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    async def invoke(name: str, arguments: dict[str, Any]) -> Any:
        result = await server.call_tool(name, arguments)
        return json.loads(result.content[0].text)

    return Framework(
        name="mcp",
        tools=tools,
        schema_of=lambda tool: tool.input_schema,
        invoke=invoke,
    )


def _rest(registry: OperationRegistry) -> Framework:
    from fastapi.testclient import TestClient

    from netforge.adapters.rest import build_app

    client = TestClient(build_app(registry))
    tools = {
        item["name"]: item
        for item in client.get("/operations").json()["operations"]
    }

    async def invoke(name: str, arguments: dict[str, Any]) -> Any:
        return client.post(f"/operations/{name}", json=arguments).json()

    return Framework(
        name="rest",
        tools=tools,
        schema_of=lambda tool: tool["request_schema"],
        invoke=invoke,
    )


def _the_frameworks(registry: OperationRegistry) -> list[Framework]:
    """Return every framework that is installed in this environment."""
    frameworks = []
    if _installed("llama-index-core"):
        frameworks.append(_llamaindex(registry))
    if _installed("pydantic-ai"):
        frameworks.append(_pydantic_ai(registry))
    if _installed("langchain-core"):
        frameworks.append(_langchain(registry))
    if _installed("mcp"):
        frameworks.append(_mcp(registry))
    if _installed("fastapi"):
        frameworks.append(_rest(registry))
    return frameworks


class TestTheAdaptersAgree:
    """Every adapter must expose the same operations, the same way.

    This is the test that makes the claim "NetForge works with any agent
    framework" something that is checked, rather than something that is
    hoped for.
    """

    def test_there_is_a_framework_to_check(self, registry):
        if not _the_frameworks(registry):
            pytest.skip("no agent framework is installed")

    def test_every_framework_has_a_tool_for_every_operation(self, registry):
        for framework in _the_frameworks(registry):
            assert set(framework.tools) == set(registry.names()), framework.name

    def test_every_framework_declares_the_same_parameters(self, registry):
        for framework in _the_frameworks(registry):
            for name, tool in framework.tools.items():
                expected = registry.get_operation(name).request_model.model_json_schema()
                declared = framework.schema_of(tool)
                assert set(declared.get("properties", {})) == set(
                    expected.get("properties", {})
                ), (framework.name, name)
                assert set(declared.get("required", [])) == set(
                    expected.get("required", [])
                ), (framework.name, name)

    def test_every_framework_returns_the_same_response(self, registry):
        operation = registry.create("configuration.validate")
        expected = asyncio.run(
            operation.run_request({"content": "{}"})
        ).model_dump(mode="json")

        for framework in _the_frameworks(registry):
            actual = asyncio.run(
                framework.invoke("configuration.validate", {"content": "{}"})
            )
            assert _without_the_timing(actual) == _without_the_timing(expected), framework.name

    def test_every_framework_refuses_an_argument_that_does_not_exist(self, registry):
        for framework in _the_frameworks(registry):
            with pytest.raises(Exception):  # noqa: B017 - the type differs per framework
                asyncio.run(framework.invoke("configuration.validate", {"nope": "x"}))


class TestPydanticAi:
    """The Pydantic AI adapter, on its own."""

    @pytest.fixture(autouse=True)
    def _the_extra_is_installed(self):
        if not _installed("pydantic-ai"):
            pytest.skip("pydantic-ai is not installed")

    def test_the_request_model_is_the_parameter_of_the_tool(self, registry):
        from netforge.adapters.pydantic_ai import build_tools

        tools = {tool.name: tool for tool in build_tools(registry)}
        tool = tools["discovery.ping"]
        assert tool.function.__annotations__["request"] is (
            registry.get_operation("discovery.ping").request_model
        )

    def test_the_schema_keeps_the_types_of_the_operation(self, registry):
        from netforge.adapters.pydantic_ai import build_tools

        tools = {tool.name: tool for tool in build_tools(registry)}
        schema = tools["discovery.service.enumerate"].function_schema.json_schema
        assert schema["properties"]["timeout"]["anyOf"][0]["type"] == "number"
        assert schema["properties"]["ports"]["type"] == "array"

    def test_an_agent_calls_the_operation(self, registry):
        """The whole loop: an agent, a tool call, the operation, the answer."""
        from pydantic_ai import Agent
        from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
        from pydantic_ai.models.function import AgentInfo, FunctionModel

        from netforge.adapters.pydantic_ai import build_tools

        tools = build_tools(registry)
        tools = [tool for tool in tools if tool.name == "configuration.validate"]

        async def model_function(messages, info: AgentInfo) -> ModelResponse:
            called = any(
                isinstance(part, ToolCallPart)
                for message in messages
                for part in message.parts
            )
            if called:
                return ModelResponse(parts=[TextPart("done")])
            return ModelResponse(
                parts=[ToolCallPart("configuration.validate", {"content": "{}"})]
            )

        agent = Agent(FunctionModel(model_function), tools=tools)
        result = asyncio.run(agent.run("validate this configuration"))

        assert result.output == "done"
        returns = [
            part.content
            for message in result.all_messages()
            for part in message.parts
            if type(part).__name__ == "ToolReturnPart"
        ]
        assert json.loads(returns[0])["operation"] == "configuration.validate"

    def test_the_agent_offers_every_operation_to_the_model(self, registry):
        """The model is offered every operation, by name."""
        from pydantic_ai.messages import ModelResponse, TextPart
        from pydantic_ai.models.function import AgentInfo, FunctionModel

        from netforge.adapters.pydantic_ai import build_agent

        offered: list[str] = []

        async def model_function(messages, info: AgentInfo) -> ModelResponse:
            offered.extend(tool.name for tool in info.function_tools)
            return ModelResponse(parts=[TextPart("done")])

        agent = build_agent(registry, model=FunctionModel(model_function))
        asyncio.run(agent.run("hello"))

        assert set(offered) == set(registry.names())


class TestLangChain:
    """The LangChain adapter, on its own."""

    @pytest.fixture(autouse=True)
    def _the_extra_is_installed(self):
        if not _installed("langchain-core"):
            pytest.skip("langchain-core is not installed")

    def test_the_request_model_is_the_schema_of_the_tool(self, registry):
        from netforge.adapters.langchain import build_tools

        tools = {tool.name: tool for tool in build_tools(registry)}
        tool = tools["discovery.ping"]
        assert tool.args_schema is registry.get_operation("discovery.ping").request_model

    def test_the_schema_keeps_the_types_of_the_operation(self, registry):
        from netforge.adapters.langchain import build_tools

        tools = {tool.name: tool for tool in build_tools(registry)}
        schema = tools["discovery.service.enumerate"].args_schema.model_json_schema()
        assert schema["properties"]["timeout"]["anyOf"][0]["type"] == "number"
        assert schema["properties"]["ports"]["type"] == "array"

    def test_a_tool_runs_the_operation(self, registry):
        from netforge.adapters.langchain import build_tools

        tools = {tool.name: tool for tool in build_tools(registry)}
        result = asyncio.run(tools["configuration.validate"].ainvoke({"content": "{}"}))
        assert json.loads(result)["operation"] == "configuration.validate"

    def test_a_tool_refuses_an_argument_that_does_not_exist(self, registry):
        from netforge.adapters.langchain import build_tools

        tools = {tool.name: tool for tool in build_tools(registry)}
        with pytest.raises(Exception):  # noqa: B017 - pydantic raises here
            asyncio.run(tools["configuration.validate"].ainvoke({"nope": "x"}))


class TestServingTheAgentAdapters:
    """The ``serve`` command prints the tools of the agent adapters."""

    @pytest.mark.parametrize(
        ("adapter", "distribution"),
        [
            ("llamaindex", "llama-index-core"),
            ("langchain", "langchain-core"),
            ("pydantic-ai", "pydantic-ai"),
        ],
    )
    def test_the_command_prints_the_tools(self, capsys, adapter, distribution):
        from netforge.adapters.cli import main

        if not _installed(distribution):
            pytest.skip(f"{distribution} is not installed")

        assert main(["serve", adapter]) == 0
        output = capsys.readouterr().out
        assert "discovery.ping" in output
        assert "tool(s)." in output
