"""The adapter layer.

Six adapters, one contract:

``cli``
    the command line -- always available, standard library only;
``rest``
    a REST API over the whole catalogue (needs the ``rest`` extra);
``mcp``
    the operations as MCP tools (needs the ``mcp`` extra);
``llamaindex``
    the operations as LlamaIndex function tools (needs the ``llamaindex``
    extra);
``langchain``
    the operations as LangChain tools (needs the ``langchain`` extra);
``pydantic-ai``
    the operations as Pydantic AI tools (needs the ``pydantic-ai`` extra).

An adapter is *optional* in the sense that it may need an extra, but it is
never *partial*: an adapter either exposes the whole catalogue or it is not
available at all.

The agent frameworks each build their own tools, so the builders are
named after the framework they serve.  ``build_tools`` is the LlamaIndex
one, and has been since the beginning; it stays that name.
"""

from __future__ import annotations

from netforge.adapters.base import Adapter, AdapterError
from netforge.adapters.cli import CliAdapter, build_parser, main
from netforge.adapters.langchain import LangChainAdapter
from netforge.adapters.langchain import build_tools as build_langchain_tools
from netforge.adapters.llamaindex import LlamaIndexAdapter, build_tools
from netforge.adapters.mcp import McpAdapter, build_server
from netforge.adapters.pydantic_ai import PydanticAiAdapter
from netforge.adapters.pydantic_ai import build_agent as build_pydantic_ai_agent
from netforge.adapters.pydantic_ai import build_tools as build_pydantic_ai_tools
from netforge.adapters.rest import RestAdapter, build_app

__all__ = [
    "Adapter",
    "AdapterError",
    "CliAdapter",
    "LangChainAdapter",
    "LlamaIndexAdapter",
    "McpAdapter",
    "PydanticAiAdapter",
    "RestAdapter",
    "build_app",
    "build_langchain_tools",
    "build_parser",
    "build_pydantic_ai_agent",
    "build_pydantic_ai_tools",
    "build_server",
    "build_tools",
    "main",
]
