"""The generator of the module documentation.

The registry is the only source of truth about what NetForge can do, and
the code already carries the prose: the module docstrings, the operation
docstrings and the Pydantic field descriptions that become the request
schema.  The documentation is therefore **derived** from the code, so it
cannot go stale.

The generator writes two things:

* the **operation pages** -- ``docs/<category>/<operation>.md``;
* the **generated blocks** of the package pages -- the operations table
  and the public API listing.

The prose around those blocks is hand-written and is never touched: the
generator replaces only what is between ``<!-- generated:NAME -->`` and
``<!-- /generated:NAME -->``.

Run it with:

    python tools/generate_docs.py

It writes only what is missing or out of date, so it is safe to run on
a clean tree -- and ``tests/test_documentation.py`` asserts that running
it changes nothing.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

#: The documentation of the project itself: the index and the architecture.
DOCS = ROOT / "docs"


def the_folder_of(category: str) -> Path:
    """The documentation folder of a package.

    The documentation of a package lives *in* the package: the folder
    belongs to the code it describes, and travels with it.
    """
    return ROOT / category / "docs"

#: The marker that opens a generated block.
BEGIN = "<!-- generated:{name} -->"

#: The marker that closes a generated block.
END = "<!-- /generated:{name} -->"

#: The kind of a value, as the JSON schema of Pydantic writes it.
_TYPE_NAMES = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "list",
    "object": "object",
    "null": "null",
}


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

def the_registry():
    """The registry of the built-in operations."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from netforge.core.bootstrap import builtin_registry

    return builtin_registry()


def the_descriptors() -> list[Any]:
    """Every built-in operation, sorted by name."""
    return the_registry().list()


# ---------------------------------------------------------------------------
# The helpers
# ---------------------------------------------------------------------------

def the_type_of(schema: dict[str, Any]) -> str:
    """The name of the type of a JSON schema, in the documentation's words.

    A schema that allows several types -- ``anyOf`` -- is written as the
    union of them, with ``null`` left out, because ``null`` means "not
    given".
    """
    if not isinstance(schema, dict):
        return "any"

    if "anyOf" in schema:
        parts = [the_type_of(part) for part in schema["anyOf"]]
        parts = [part for part in parts if part != "null"]
        if not parts:
            return "null"
        if len(parts) == 1:
            return parts[0]
        return " or ".join(parts)

    if "enum" in schema:
        return " or ".join(json.dumps(value) for value in schema["enum"])

    kind = schema.get("type")
    if kind is None:
        return "any"
    if kind == "array":
        items = schema.get("items") or {}
        return f"list of {the_type_of(items)}"
    return _TYPE_NAMES.get(kind, kind)


def the_default_of(schema: dict[str, Any]) -> str:
    """The default of a parameter, as the documentation writes it."""
    if not isinstance(schema, dict):
        return "—"
    if "default" not in schema:
        return "—"
    value = schema["default"]
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "`true`" if value else "`false`"
    if isinstance(value, (int, float)):
        return f"`{value}`"
    return f"`{json.dumps(value)}`"


def _characters(count: int) -> str:
    """``character`` or ``characters`` — the number decides."""
    return "character" if count == 1 else "characters"


def the_constraints_of(schema: dict[str, Any]) -> str:
    """The constraints of a parameter, in one phrase."""
    if not isinstance(schema, dict):
        return ""
    parts: list[str] = []
    if "minimum" in schema:
        parts.append(f"at least {schema['minimum']}")
    if "maximum" in schema:
        parts.append(f"at most {schema['maximum']}")
    if "exclusiveMinimum" in schema:
        parts.append(f"more than {schema['exclusiveMinimum']}")
    if "exclusiveMaximum" in schema:
        parts.append(f"less than {schema['exclusiveMaximum']}")
    if "minLength" in schema:
        parts.append(f"at least {schema['minLength']} {_characters(schema['minLength'])}")
    if "maxLength" in schema:
        parts.append(f"at most {schema['maxLength']} {_characters(schema['maxLength'])}")
    if "minItems" in schema:
        parts.append(f"at least {schema['minItems']} items")
    if "maxItems" in schema:
        parts.append(f"at most {schema['maxItems']} items")
    if "pattern" in schema:
        parts.append(f"matches `{schema['pattern']}`")
    return ", ".join(parts)


def the_parameters_of(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """The parameters of a request, in the order the schema declares them."""
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    parameters = []
    for name, definition in properties.items():
        parameters.append(
            {
                "name": name,
                "type": the_type_of(definition),
                "default": the_default_of(definition),
                "required": name in required,
                "constraints": the_constraints_of(definition),
                "description": (definition or {}).get("description", ""),
            }
        )
    return parameters


def the_docstring_of(implementation: str) -> str:
    """The docstring of the module that implements an operation."""
    module_name = implementation.split(":", 1)[0]
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return ""
    return inspect.getdoc(module) or ""


def the_public_api(package: str) -> list[str]:
    """The public API of a package: the names it exports, and their shapes."""
    try:
        module = importlib.import_module(f"netforge.{package}")
    except ImportError:
        return []

    lines: list[str] = []
    for name in getattr(module, "__all__", []):
        member = getattr(module, name, None)
        if member is None:
            continue
        if inspect.isclass(member):
            lines.append(f"class {name}{the_signature_of(member)}")
        elif inspect.isfunction(member):
            lines.append(f"def {name}{the_signature_of(member)}")
        else:
            lines.append(f"{name} {the_signature_of(member)}")
    return lines


def the_annotation_of(parameter: inspect.Parameter) -> str:
    """The annotation of a parameter, without the quotes.

    ``from __future__ import annotations`` makes every annotation a
    string, and a signature written with the quotes is unreadable.
    """
    annotation = parameter.annotation
    if annotation is inspect.Parameter.empty:
        return ""
    text = str(annotation)
    if len(text) > 1 and text.startswith("'") and text.endswith("'"):
        text = text[1:-1]
    return f": {text}"


def the_signature_parameters(parameters: list[inspect.Parameter]) -> str:
    """The parameters of a signature, as one string."""
    parts = []
    keyword_only = False
    for parameter in parameters:
        if parameter.name == "self":
            continue
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY and not keyword_only:
            parts.append("*")
            keyword_only = True
        part = parameter.name + the_annotation_of(parameter)
        if parameter.default is not inspect.Parameter.empty:
            part += f" = {parameter.default!r}"
        parts.append(part)
    return ", ".join(parts)


def the_type_name(annotation: Any) -> str:
    """The name of a type, in the way the documentation writes it.

    ``str`` is a class, and ``str(str)`` is ``<class 'str'>`` — which is
    not what a reader wants to see.
    """
    if annotation is None:
        return ""
    if isinstance(annotation, type):
        return annotation.__name__
    text = str(annotation)
    if len(text) > 1 and text.startswith("'") and text.endswith("'"):
        text = text[1:-1]
    return text


def the_model_fields_of(member: Any) -> str:
    """The fields of a Pydantic model, as one string.

    A model is keyword-only, and the constructor of Pydantic tells
    nothing about the fields — so the fields are what is written.
    """
    parts = []
    for name, field in member.model_fields.items():
        annotation = the_type_name(field.annotation)
        part = f"{name}: {annotation}" if annotation else name
        if not field.is_required():
            try:
                default = field.get_default(call_default_factory=True)
            except TypeError:
                default = field.get_default()
            part += f" = {default!r}"
        parts.append(part)
    if not parts:
        return "()"
    return f"(*, {', '.join(parts)})"


def the_return_of(signature: inspect.Signature) -> str:
    """The return annotation of a signature, without the quotes."""
    if signature.return_annotation is inspect.Signature.empty:
        return ""
    text = str(signature.return_annotation)
    if len(text) > 1 and text.startswith("'") and text.endswith("'"):
        text = text[1:-1]
    return f" -> {text}"


def the_signature_of(member: Any) -> str:
    """The shape of a name, as one line.

    A class is written as ``class Name(...)``, a function as
    ``def name(...) -> ...``, and a constant as ``NAME = value``.
    """
    if inspect.isclass(member):
        if hasattr(member, "model_fields"):
            return the_model_fields_of(member)
        if member.__init__ is object.__init__:
            return "()"
        try:
            signature = inspect.signature(member.__init__)
        except (TypeError, ValueError):
            return "()"
        return f"({the_signature_parameters(list(signature.parameters.values()))})"

    if inspect.isfunction(member):
        try:
            signature = inspect.signature(member)
        except (TypeError, ValueError):
            return "()"
        return (
            f"({the_signature_parameters(list(signature.parameters.values()))})"
            f"{the_return_of(signature)}"
        )

    if inspect.ismodule(member):
        return "(a module)"

    if callable(member):
        return "()"
    # A constant: the value, cut short.  A whole dictionary in the
    # listing is noise, not documentation.
    rendered = repr(member)
    if len(rendered) > 60:
        rendered = rendered[:57] + "..."
    return f"= {rendered}"


def the_page_name(operation: str, category: str) -> str:
    """The file name of the page of an operation."""
    prefix = f"{category}."
    if operation.startswith(prefix):
        return operation[len(prefix):]
    return operation


# ---------------------------------------------------------------------------
# The operation page
# ---------------------------------------------------------------------------

def the_operation_page(descriptor: Any) -> str:
    """The page of one operation."""
    name = descriptor.name
    category = descriptor.category.value
    risk = int(descriptor.risk_level)
    # The label of the enum is the word the code uses, and the word
    # `netforge list` prints.
    risk_label = descriptor.risk_level.label

    lines = [
        f"# `{name}`",
        "",
        f"> {descriptor.summary}",
        "",
        f"**Risk:** {risk_label} (level {risk})  ",
        f"**Category:** {category}  ",
        f"**Tags:** {', '.join(f'`{tag}`' for tag in sorted(descriptor.tags)) or '—'}  ",
        f"**Implementation:** `{descriptor.implementation}`",
        "",
        "---",
        "",
        "## What it does",
        "",
        descriptor.description or descriptor.summary,
        "",
    ]

    if descriptor.aliases:
        lines += [
            "**Also known as:** "
            + ", ".join(f"`{alias}`" for alias in descriptor.aliases),
            "",
        ]

    if descriptor.requires_privilege:
        lines += [
            "> **This operation needs elevated privileges.**  It is refused "
            "when the process does not have them.",
            "",
        ]

    parameters = the_parameters_of(descriptor.request_schema)
    lines += ["## The request", ""]
    if parameters:
        lines += [
            "| Parameter | Type | Default | What it is |",
            "|---|---|---|---|",
        ]
        for parameter in parameters:
            description = parameter["description"].replace("|", "\\|")
            if parameter["constraints"]:
                description = f"{description} ({parameter['constraints']})"
            if parameter["required"]:
                description = f"**Required.** {description}"
            lines.append(
                f"| `{parameter['name']}` | {parameter['type']} | "
                f"{parameter['default']} | {description} |"
            )
    else:
        lines.append("It takes no parameters.")

    lines += ["", "## The response", ""]
    lines += the_response_section(descriptor)

    lines += [
        "",
        "## Using it",
        "",
        "### From the command line",
        "",
        "```console",
        f"$ netforge run {name}" + the_cli_flags(parameters),
        "```",
        "",
        "The values above are placeholders.  The request may also be given "
        "as a JSON object, which the flags are laid over:",
        "",
        "```console",
        f"$ netforge run {name}" + the_cli_request(parameters),
        "```",
        "",
        "### From Python",
        "",
        "```python",
        "from netforge.core.bootstrap import builtin_registry",
        "",
        "registry = builtin_registry()",
        f'operation = registry.create("{name}")',
        f"result = await operation.run({the_python_arguments(parameters)})",
        "```",
        "",
    ]

    docstring = the_docstring_of(descriptor.implementation)
    if docstring:
        lines += ["## How it works", "", docstring, ""]

    lines += [
        "## See also",
        "",
        f"* [the `{category}` package](README.md) — every operation it publishes",
        "* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together",
        "* [the documentation index](../../docs/README.md)",
        "",
    ]

    return "\n".join(lines)


def the_response_section(descriptor: Any) -> list[str]:
    """The response section of an operation page."""
    schema = descriptor.response_schema or {}
    properties = schema.get("properties") or {}
    if not properties:
        return ["It returns the standard response envelope."]

    lines = [
        "| Field | Type | What it is |",
        "|---|---|---|",
    ]
    for name, definition in properties.items():
        description = (definition or {}).get("description", "").replace("|", "\\|")
        lines.append(f"| `{name}` | {the_type_of(definition)} | {description} |")
    return lines


def the_placeholder_of(kind: str) -> Any:
    """A placeholder of the shape of a value, for the examples."""
    if kind in ("integer", "number"):
        return 0
    if kind == "boolean":
        return False
    if kind.startswith("list"):
        return []
    if kind == "object":
        return {}
    return "..."


def the_cli_flags(parameters: list[dict[str, Any]]) -> str:
    """The command line of an operation.

    The parameters of the operation are given as flags, the way a person
    would type them.
    """
    parts = []
    for parameter in parameters:
        if not parameter["required"]:
            continue
        name = parameter["name"].replace("_", "-")
        kind = parameter["type"]
        if kind == "boolean":
            parts.append(f" --{name}")
        elif kind == "string":
            parts.append(f' --{name} "..."')
        elif kind.startswith("list"):
            parts.append(f" --{name} []")
        else:
            parts.append(f" --{name} 0")
    return "".join(parts)


def the_cli_request(parameters: list[dict[str, Any]]) -> str:
    """The request of an operation, as the JSON object the adapter takes."""
    payload = {
        parameter["name"]: the_placeholder_of(parameter["type"])
        for parameter in parameters
        if parameter["required"]
    }
    return " --request '" + json.dumps(payload) + "'"


def the_python_arguments(parameters: list[dict[str, Any]]) -> str:
    """The Python arguments of an operation."""
    return ", ".join(
        f"{parameter['name']}=..." for parameter in parameters if parameter["required"]
    )


# ---------------------------------------------------------------------------
# The generated blocks of the package page
# ---------------------------------------------------------------------------

def the_operations_block(descriptors: list[Any]) -> str:
    """The operations table of a package."""
    lines = [
        "| Operation | Risk | What it does |",
        "|---|---|---|",
    ]
    for descriptor in descriptors:
        risk_label = descriptor.risk_level.label
        page = the_page_name(descriptor.name, descriptor.category.value)
        lines.append(
            f"| [`{descriptor.name}`]({page}.md) | {risk_label} | "
            f"{descriptor.summary} |"
        )
    return "\n".join(lines)


def the_public_api_block(package: str) -> str:
    """The public API listing of a package."""
    lines = the_public_api(package)
    if not lines:
        return "_Nothing is exported._"
    return "```text\n" + "\n".join(lines) + "\n```"


# ---------------------------------------------------------------------------
# The writing
# ---------------------------------------------------------------------------

def replace_block(text: str, name: str, body: str) -> str:
    """Replace the content between the markers of a generated block.

    A block that is not there yet is added at the end of the text, so a
    package page that has never been generated still gets its tables.
    """
    begin = BEGIN.format(name=name)
    end = END.format(name=name)
    replacement = f"{begin}\n{body}\n{end}"

    if begin in text and end in text:
        head, _, rest = text.partition(begin)
        _, _, tail = rest.partition(end)
        return f"{head}{replacement}{tail}"

    separator = "\n\n" if text.strip() else ""
    return f"{text.rstrip()}{separator}{replacement}\n"


def write_if_changed(path: Path, text: str, write: bool = True) -> bool:
    """Write the file when the content differs.  Returns whether it differs.

    With ``write=False`` nothing is written, and the answer is the same:
    whether the file on disk is already what the generator would write.
    That is what ``--check`` asks.
    """
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return True


def generate(write: bool = True) -> list[str]:
    """Generate the documentation.  Returns the files that changed."""
    descriptors = the_descriptors()
    by_category: dict[str, list[Any]] = {}
    for descriptor in descriptors:
        by_category.setdefault(descriptor.category.value, []).append(descriptor)

    changed: list[str] = []

    for category, category_descriptors in sorted(by_category.items()):
        folder = the_folder_of(category)

        # -- the operation pages -----------------------------------------
        for descriptor in category_descriptors:
            page = folder / f"{the_page_name(descriptor.name, category)}.md"
            text = the_operation_page(descriptor)
            if write_if_changed(page, text, write=write):
                changed.append(str(page.relative_to(ROOT)))

        # -- the package page ---------------------------------------------
        entry = folder / "README.md"
        if not entry.is_file():
            continue
        text = entry.read_text(encoding="utf-8")
        text = replace_block(
            text, "operations", the_operations_block(category_descriptors)
        )
        text = replace_block(text, "public-api", the_public_api_block(category))
        if write_if_changed(entry, text, write=write):
            changed.append(str(entry.relative_to(ROOT)))

    return changed


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit non-zero when something is out of date.",
    )
    arguments = parser.parse_args(list(argv) if argv is not None else None)

    if arguments.check:
        changed = generate(write=False)
        if changed:
            print("These files are out of date:")
            for name in changed:
                print(f"  {name}")
            return 1
        print("The documentation is up to date.")
        return 0

    changed = generate(write=True)
    if changed:
        print(f"{len(changed)} files written:")
        for name in changed:
            print(f"  {name}")
    else:
        print("Nothing changed — the documentation was up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
