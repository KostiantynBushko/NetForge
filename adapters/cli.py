"""The command-line adapter.

The CLI is built on :mod:`argparse` from the standard library, so it is
available in every installation of NetForge, with no extra to install.

The commands are:

``netforge list``
    the catalogue of operations, grouped by category;

``netforge describe <operation>``
    one operation in full, with its request schema;

``netforge categories``
    the capability categories and what is in them;

``netforge risk``
    the risk profile of the catalogue;

``netforge run <operation> --request '<json>'``
    run an operation and print its response as JSON;

``netforge serve``
    start one of the other adapters -- ``rest``, ``mcp`` or ``llamaindex``.

The exit code is meaningful: ``0`` for success, ``1`` for an error, ``2``
for a usage error.  That is what a script wants.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Sequence

from netforge.adapters.base import Adapter, AdapterError
from netforge.core.bootstrap import load_builtin_operations
from netforge.core.context import ExecutionContext
from netforge.core.exceptions import NetForgeError
from netforge.core.logging import configure_logging, get_logger
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel
from netforge.registry.registry import OperationRegistry

__all__ = ["CliAdapter", "build_parser", "main"]

_logger = get_logger("adapters.cli")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


class CliAdapter(Adapter):
    """The command-line adapter."""

    name = "cli"
    description = "The command-line interface, built on the standard library."

    def __init__(self, registry: OperationRegistry | None = None) -> None:
        self.registry = registry if registry is not None else load_builtin_operations()

    def available(self) -> bool:
        """The CLI is always available."""
        return True

    def describe(self) -> dict[str, Any]:
        """Return a description of the adapter."""
        return {
            "name": self.name,
            "description": self.description,
            "available": True,
            "operations": len(self.registry),
        }


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser of the ``netforge`` command."""
    parser = argparse.ArgumentParser(
        prog="netforge",
        description="NetForge -- a modular network operations and security toolkit.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="The log level (default: WARNING).",
    )
    parser.add_argument(
        "--max-risk",
        default=None,
        help="The highest risk level an operation may run at (1-4).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the output as JSON, where the command has a choice.",
    )

    # The global options are repeated on every subcommand, so that both
    # "netforge --json list" and "netforge list --json" work.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        help="Print the output as JSON, where the command has a choice.",
    )

    subparsers = parser.add_subparsers(dest="command")

    listing = subparsers.add_parser(
        "list", parents=[common], help="List the operations, grouped by category."
    )
    listing.add_argument("--category", default=None, help="Only this category.")
    listing.add_argument("--risk", default=None, help="Only operations at or below this risk level.")
    listing.add_argument("--tag", default=None, help="Only operations with this tag.")
    listing.add_argument("--query", default=None, help="Only operations matching this text.")

    describe = subparsers.add_parser(
        "describe", parents=[common], help="Describe one operation in full."
    )
    describe.add_argument("operation", help="The name of the operation.")

    subparsers.add_parser(
        "categories", parents=[common], help="Show the capability categories."
    )
    subparsers.add_parser(
        "risk", parents=[common], help="Show the risk profile of the catalogue."
    )

    run = subparsers.add_parser("run", parents=[common], help="Run an operation.")
    run.add_argument("operation", help="The name of the operation.")
    run.add_argument(
        "--request",
        default="{}",
        help="The request, as a JSON object (default: {}).",
    )
    run.add_argument("--timeout", type=float, default=None, help="The time budget, in seconds.")

    serve = subparsers.add_parser("serve", help="Start one of the other adapters.")
    serve.add_argument(
        "adapter",
        choices=["rest", "mcp", "llamaindex"],
        help="The adapter to start.",
    )
    serve.add_argument("--host", default="127.0.0.1", help="The address to bind to.")
    serve.add_argument("--port", type=int, default=8080, help="The port to bind to.")

    return parser


def _print_table(rows: list[list[str]], headers: list[str]) -> None:
    """Print rows as a simple aligned table."""
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def _row(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(cells)).rstrip()

    print(_row(headers))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print(_row(row))


def _command_list(
    args: argparse.Namespace,
    registry: OperationRegistry,
    ceiling: RiskLevel | None = None,
) -> int:
    # The global --max-risk is a ceiling: it restricts the catalogue to what
    # the caller is allowed to run.  The --risk filter narrows it further.
    effective = ceiling
    if args.risk:
        requested = RiskLevel.parse(args.risk)
        effective = requested if effective is None else min(effective, requested)

    descriptors = registry.list(
        category=args.category,
        max_risk=effective,
        tag=args.tag,
        query=args.query,
    )
    if args.json:
        print(json.dumps([descriptor.model_dump(mode="json") for descriptor in descriptors], indent=2))
        return EXIT_OK

    current: str | None = None
    for descriptor in descriptors:
        if descriptor.category != current:
            current = descriptor.category
            print()
            print(f"{CapabilityCategory(descriptor.category).label}")
            print("-" * len(CapabilityCategory(descriptor.category).label))
        summary = descriptor.summary
        print(f"  {descriptor.name:<34} L{descriptor.risk_level}  {summary}")
    print()
    print(f"{len(descriptors)} operation(s).")
    return EXIT_OK


def _command_describe(args: argparse.Namespace, registry: OperationRegistry) -> int:
    descriptor = registry.get(args.operation)
    if args.json:
        print(json.dumps(descriptor.model_dump(mode="json"), indent=2))
        return EXIT_OK

    print(f"name        {descriptor.name}")
    print(f"category    {descriptor.category}")
    print(f"risk level  L{descriptor.risk_level} ({descriptor.risk_level.label})")
    print(f"privileges  {'required' if descriptor.requires_privilege else 'not required'}")
    if descriptor.tags:
        print(f"tags        {', '.join(descriptor.tags)}")
    if descriptor.description:
        print()
        print(descriptor.description)
    print()
    print("request schema")
    print(json.dumps(descriptor.request_schema, indent=2))
    return EXIT_OK


def _command_categories(args: argparse.Namespace, registry: OperationRegistry) -> int:
    grouped = registry.categories()
    if args.json:
        print(json.dumps(grouped, indent=2))
        return EXIT_OK

    for category, names in grouped.items():
        label = CapabilityCategory(category).label
        print(f"{label} ({len(names)})")
        for name in names:
            print(f"  {name}")
        print()
    return EXIT_OK


def _command_risk(args: argparse.Namespace, registry: OperationRegistry) -> int:
    profile = registry.risk_profile()
    if args.json:
        print(json.dumps(profile, indent=2))
        return EXIT_OK

    for level in RiskLevel:
        names = registry.list(max_risk=level)
        print(f"L{level}  {level.label:<20} {len(names):>3} operation(s)")
    print()
    print(json.dumps(profile, indent=2))
    return EXIT_OK


def _command_run(args: argparse.Namespace, registry: OperationRegistry, context: ExecutionContext) -> int:
    try:
        payload = json.loads(args.request)
    except json.JSONDecodeError as exc:
        print(f"the request is not valid JSON: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if not isinstance(payload, dict):
        print("the request must be a JSON object", file=sys.stderr)
        return EXIT_USAGE

    operation = registry.create(args.operation)
    response = asyncio.run(operation.run_request(payload, context))
    print(json.dumps(response.model_dump(mode="json"), indent=2))
    return EXIT_OK


def _command_serve(args: argparse.Namespace, registry: OperationRegistry) -> int:
    if args.adapter == "rest":
        from netforge.adapters.rest import serve_rest

        return serve_rest(registry, host=args.host, port=args.port)
    if args.adapter == "mcp":
        from netforge.adapters.mcp import serve_mcp

        return serve_mcp(registry)
    from netforge.adapters.llamaindex import serve_llamaindex

    return serve_llamaindex(registry)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``netforge`` command and return its exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)

    if not args.command:
        parser.print_help()
        return EXIT_USAGE

    registry = load_builtin_operations()

    max_risk = RiskLevel.SYSTEM_MODIFICATION
    if args.max_risk:
        try:
            max_risk = RiskLevel.parse(args.max_risk)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_USAGE

    context = ExecutionContext(max_risk=max_risk)

    try:
        if args.command == "list":
            return _command_list(args, registry, max_risk)
        if args.command == "describe":
            return _command_describe(args, registry)
        if args.command == "categories":
            return _command_categories(args, registry)
        if args.command == "risk":
            return _command_risk(args, registry)
        if args.command == "run":
            if args.timeout is not None:
                context.timeout = args.timeout
            return _command_run(args, registry, context)
        if args.command == "serve":
            return _command_serve(args, registry)
    except NetForgeError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except AdapterError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:  # pragma: no cover - interactive
        print("interrupted", file=sys.stderr)
        return EXIT_ERROR

    parser.print_help()
    return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
