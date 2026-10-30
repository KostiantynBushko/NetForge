"""The parameters of an operation, taken from the command line.

The command line of ``netforge run`` takes the parameters of the operation
as flags, the way a person would type them::

    netforge run discovery.service.enumerate --host 192.168.0.13

The request is still accepted as JSON -- ``--request '{"host": ...}'`` --
and the flags are laid over it.  The two forms can be mixed.

The types come from the request schema of the operation, so the value on
the command line is coerced exactly as a value that came in as JSON
would be: a port is a number, a list is a list, and a value that does
not fit is refused before the operation is run.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

__all__ = [
    "the_flags",
    "the_payload",
]


class ParameterError(Exception):
    """A parameter on the command line does not fit the operation."""


def the_type_of(schema: dict[str, Any]) -> str:
    """The type of a JSON schema property, in the words of the coercion.

    A property that allows several types -- ``anyOf`` -- is taken as the
    type that is not ``null``: ``null`` means "not given", and a flag
    that is given is never null.
    """
    if not isinstance(schema, dict):
        return "string"

    if "anyOf" in schema:
        for part in schema["anyOf"]:
            kind = the_type_of(part)
            if kind != "null":
                return kind
        return "string"

    kind = schema.get("type")
    if kind == "array":
        items = schema.get("items") or {}
        inner = the_type_of(items)
        return "list of " + inner if inner != "string" else "list"
    if kind is None:
        return "string"
    return kind


def the_flags(extras: Sequence[str]) -> dict[str, str | None]:
    """The flags of the parameters, from the arguments argparse did not know.

    ``--host 192.168.0.13`` and ``--host=192.168.0.13`` are the same
    flag; ``--verbose`` on its own is a flag that is true.
    """
    flags: dict[str, str | None] = {}
    index = 0
    while index < len(extras):
        token = extras[index]
        if not token.startswith("--"):
            raise ParameterError(f"unexpected argument: {token}")

        name, separator, value = token[2:].partition("=")
        name = name.replace("-", "_")
        if separator:
            flags[name] = value
            index += 1
            continue

        following = extras[index + 1] if index + 1 < len(extras) else None
        if following is not None and not following.startswith("--"):
            flags[name] = following
            index += 2
        else:
            flags[name] = None
            index += 1
    return flags


def the_value_of(name: str, raw: str | None, schema: dict[str, Any]) -> Any:
    """Coerce the value of a flag to the type of the parameter."""
    kind = the_type_of(schema)

    if kind == "boolean":
        if raw is None:
            return True
        lowered = raw.strip().lower()
        if lowered in ("true", "yes", "on", "1"):
            return True
        if lowered in ("false", "no", "off", "0"):
            return False
        raise ParameterError(
            f"the parameter --{name.replace('_', '-')} must be true or false, not {raw!r}"
        )

    if raw is None:
        raise ParameterError(
            f"the parameter --{name.replace('_', '-')} needs a value"
        )

    if kind == "integer":
        try:
            return int(raw)
        except ValueError:
            raise ParameterError(
                f"the parameter --{name.replace('_', '-')} must be a whole number, "
                f"not {raw!r}"
            ) from None

    if kind == "number":
        try:
            return float(raw)
        except ValueError:
            raise ParameterError(
                f"the parameter --{name.replace('_', '-')} must be a number, "
                f"not {raw!r}"
            ) from None

    if kind.startswith("list"):
        return the_list_of(name, raw, schema)

    if kind == "object":
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            raise ParameterError(
                f"the parameter --{name.replace('_', '-')} must be a JSON object, "
                f"not {raw!r}"
            ) from None
        if not isinstance(value, dict):
            raise ParameterError(
                f"the parameter --{name.replace('_', '-')} must be a JSON object, "
                f"not {raw!r}"
            )
        return value

    return raw


def the_list_of(name: str, raw: str | None, schema: dict[str, Any]) -> list[Any]:
    """Coerce the value of a flag to a list.

    A list is written as JSON -- ``'[22, 80]'`` -- or as a comma
    separated list -- ``'22,80'``.
    """
    if raw is None:
        raise ParameterError(
            f"the parameter --{name.replace('_', '-')} needs a value"
        )

    text = raw.strip()
    if text.startswith("["):
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            raise ParameterError(
                f"the parameter --{name.replace('_', '-')} must be a list, not {raw!r}"
            ) from None
        if not isinstance(value, list):
            raise ParameterError(
                f"the parameter --{name.replace('_', '-')} must be a list, not {raw!r}"
            )
        return value

    inner = the_type_of(schema.get("items") or {})
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if inner == "integer":
        try:
            return [int(part) for part in parts]
        except ValueError:
            raise ParameterError(
                f"the parameter --{name.replace('_', '-')} must be a list of "
                f"whole numbers, not {raw!r}"
            ) from None
    if inner == "number":
        try:
            return [float(part) for part in parts]
        except ValueError:
            raise ParameterError(
                f"the parameter --{name.replace('_', '-')} must be a list of "
                f"numbers, not {raw!r}"
            ) from None
    return parts


def the_payload(
    flags: dict[str, str | None], properties: dict[str, Any]
) -> dict[str, Any]:
    """The values of the flags, as the request of the operation.

    A flag that names no parameter of the operation is refused, and the
    refusal names the parameters there are.
    """
    payload: dict[str, Any] = {}
    for name, raw in flags.items():
        schema = properties.get(name)
        if schema is None:
            accepted = ", ".join(sorted(properties)) or "none"
            raise ParameterError(
                f"unknown parameter --{name.replace('_', '-')}; "
                f"the parameters of this operation are: {accepted}"
            )
        payload[name] = the_value_of(name, raw, schema)
    return payload
