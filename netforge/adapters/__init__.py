"""The adapter layer.

Four adapters, one contract:

``cli``
    the command line -- always available, standard library only;
``rest``
    a REST API over the whole catalogue (needs the ``rest`` extra);
``mcp``
    the operations as MCP tools (needs the ``mcp`` extra);
``llamaindex``
    the operations as LlamaIndex function tools (needs the ``llamaindex``
    extra).

An adapter is *optional* in the sense that it may need an extra, but it is
never *partial*: an adapter either exposes the whole catalogue or it is not
available at all.
"""

from __future__ import annotations

from netforge.adapters.base import Adapter, AdapterError
from netforge.adapters.cli import CliAdapter, build_parser, main
from netforge.adapters.llamaindex import LlamaIndexAdapter, build_tools
from netforge.adapters.mcp import McpAdapter, build_server
from netforge.adapters.rest import RestAdapter, build_app

__all__ = [
    "Adapter",
    "AdapterError",
    "CliAdapter",
    "LlamaIndexAdapter",
    "McpAdapter",
    "RestAdapter",
    "build_app",
    "build_parser",
    "build_server",
    "build_tools",
    "main",
]
