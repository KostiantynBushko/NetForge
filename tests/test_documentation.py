"""The documentation must match the code.

The registry is the only source of truth about what NetForge can do.  The
documentation is derived from it, and these tests are what keeps the
derivation honest: the documentation of a package lives in the package, a
package that publishes an operation has a page for it, the page names the
operation, the top-level README links to the entry point of every
package, and every link in the documentation resolves.

The tests are the reason the documentation cannot quietly rot.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from netforge.core.bootstrap import builtin_registry  # noqa: E402

#: The packages of the project, as the distribution declares them.
PACKAGES = [
    "adapters",
    "analysis",
    "capture",
    "configuration",
    "connectivity",
    "core",
    "discovery",
    "dns",
    "emulation",
    "manipulation",
    "sentinel",
    "models",
    "plugins",
    "protocols",
    "registry",
    "security",
]

#: A link inside a markdown document.
LINK = re.compile(r"\]\(([^)]+)\)")

#: A link that is not a link to a file.
NOT_A_FILE = re.compile(r"^(https?:|mailto:|#)")


@pytest.fixture(scope="module")
def registry():
    """The registry of the built-in operations."""
    return builtin_registry()


@pytest.fixture(scope="module")
def descriptors(registry):
    """Every built-in operation, sorted by name."""
    return registry.list()


def the_packages(descriptors) -> dict[str, list]:
    """The operations grouped by the package that publishes them.

    The package is the first part of the name of the operation, not its
    category: two packages may publish operations of the same category.
    """
    grouped: dict[str, list] = {}
    for descriptor in descriptors:
        grouped.setdefault(descriptor.name.split(".", 1)[0], []).append(descriptor)
    return grouped


def the_folder_of(package: str) -> Path:
    """The documentation folder of a package."""
    return ROOT / package / "docs"


def the_entry_of(package: str) -> Path:
    """The entry point of the documentation of a package."""
    return the_folder_of(package) / "README.md"


def the_page_of(operation: str) -> Path:
    """The path of the page of an operation."""
    package = operation.split(".", 1)[0]
    prefix = f"{package}."
    name = operation[len(prefix):] if operation.startswith(prefix) else operation
    return the_folder_of(package) / f"{name}.md"


class TestTheDocumentationLivesInThePackage:
    """The documentation of a package belongs to the package."""

    def test_every_package_has_a_documentation_folder(self):
        missing = [
            package
            for package in PACKAGES
            if not the_folder_of(package).is_dir()
        ]
        assert missing == [], f"these packages have no docs folder: {missing}"

    def test_every_package_has_an_entry_point(self):
        missing = [
            package for package in PACKAGES if not the_entry_of(package).is_file()
        ]
        assert missing == [], f"these packages have no entry point: {missing}"

    def test_the_entry_point_is_inside_the_package(self):
        for package in PACKAGES:
            entry = the_entry_of(package)
            assert entry.parent.parent.name == package, entry

    def test_no_documentation_is_left_in_the_project_folder(self):
        # The root folder holds the documents of the project itself: the
        # index, the architecture, and the guides.  The documentation of
        # a package lives in the package.
        loose = sorted(path.name for path in DOCS.glob("*.md"))
        assert loose == ["ARCHITECTURE.md", "README.md", "SENTINEL.md"], loose


class TestEveryOperationHasAPage:
    """The pages of the operations."""

    def test_every_operation_has_a_page(self, descriptors):
        missing = [
            descriptor.name
            for descriptor in descriptors
            if not the_page_of(descriptor.name).is_file()
        ]
        assert missing == [], f"these operations have no page: {missing}"

    def test_the_page_names_the_operation(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name)
            text = page.read_text(encoding="utf-8")
            assert f"# `{descriptor.name}`" in text, page

    def test_the_page_carries_the_summary(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name)
            text = page.read_text(encoding="utf-8")
            assert descriptor.summary in text, page

    def test_the_page_carries_the_risk(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name)
            text = page.read_text(encoding="utf-8")
            assert descriptor.risk_level.label in text, page

    def test_the_page_documents_every_request_parameter(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name)
            text = page.read_text(encoding="utf-8")
            properties = (descriptor.request_schema or {}).get("properties") or {}
            for name in properties:
                assert f"`{name}`" in text, f"{page}: the parameter {name}"

    def test_the_page_documents_every_response_field(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name)
            text = page.read_text(encoding="utf-8")
            properties = (descriptor.response_schema or {}).get("properties") or {}
            for name in properties:
                assert f"`{name}`" in text, f"{page}: the field {name}"

    def test_the_page_links_to_the_package(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name)
            text = page.read_text(encoding="utf-8")
            assert "](README.md)" in text, page


class TestEveryPackageHasAnEntryPoint:
    """The folders of the packages."""

    def test_the_entry_point_lists_every_operation(self, descriptors):
        for package, operations in the_packages(descriptors).items():
            text = the_entry_of(package).read_text(encoding="utf-8")
            for descriptor in operations:
                assert descriptor.name in text, f"{package}: {descriptor.name}"

    def test_the_entry_point_lists_the_public_api(self, descriptors):
        for package in the_packages(descriptors):
            text = the_entry_of(package).read_text(encoding="utf-8")
            assert "<!-- generated:public-api -->" in text, package

    def test_the_entry_point_links_to_its_operations(self, descriptors):
        for package, operations in the_packages(descriptors).items():
            text = the_entry_of(package).read_text(encoding="utf-8")
            for descriptor in operations:
                page = the_page_of(descriptor.name)
                assert f"]({page.name})" in text, f"{package}: {descriptor.name}"


class TestTheCommandLineExamples:
    """The examples must be the ones the adapter actually takes.

    The parameters of an operation are given as flags, and the request
    may also be given as a JSON object.  An example that shows the wrong
    command line is worse than no example at all.
    """

    def the_example(self, text: str) -> str:
        """The request of the command-line example of a page."""
        match = re.search(r"\$ netforge run \S+ --request '([^']+)'", text)
        assert match is not None, "the page has no command-line example"
        return match.group(1)

    def test_every_example_is_valid_json(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name)
            payload = json.loads(self.the_example(page.read_text(encoding="utf-8")))
            assert isinstance(payload, dict), page

    def test_every_example_carries_the_required_parameters(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name)
            text = page.read_text(encoding="utf-8")
            payload = json.loads(self.the_example(text))
            schema = descriptor.request_schema or {}
            for name in schema.get("required") or []:
                assert name in payload, f"{page}: the required parameter {name}"

    def test_every_example_names_the_operation(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name)
            text = page.read_text(encoding="utf-8")
            assert f"$ netforge run {descriptor.name} " in text, page

    def test_every_example_shows_the_parameters_as_flags(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name)
            text = page.read_text(encoding="utf-8")
            schema = descriptor.request_schema or {}
            for name in schema.get("required") or []:
                flag = f"--{name.replace('_', '-')}"
                assert flag in text, f"{page}: the flag {flag}"


class TestTheTopLevelReadme:
    """The entry point of every package has to be reachable from the README."""

    def test_the_readme_links_to_every_entry_point(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        missing = [
            package
            for package in PACKAGES
            if f"{package}/docs/README.md" not in text
        ]
        assert missing == [], f"the README does not link to: {missing}"

    def test_the_readme_links_to_the_documentation_index(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        assert "docs/README.md" in text


class TestEveryLinkResolves:
    """A link that does not resolve is a broken door."""

    def the_documents(self):
        yield from sorted(DOCS.rglob("*.md"))
        for package in PACKAGES:
            yield from sorted(the_folder_of(package).rglob("*.md"))

    def test_every_link_resolves(self):
        broken = []
        for path in self.the_documents():
            for target in LINK.findall(path.read_text(encoding="utf-8")):
                if NOT_A_FILE.match(target):
                    continue
                # the anchor of a link to a heading of the same document
                clean = target.split("#", 1)[0]
                if not clean:
                    continue
                resolved = (path.parent / clean).resolve()
                if not resolved.exists():
                    broken.append(f"{path.relative_to(ROOT)} -> {target}")
        assert broken == [], "these links do not resolve:\n" + "\n".join(broken)


class TestTheGeneratorIsHonest:
    """The documentation must be what the generator writes."""

    def test_the_signature_does_not_depend_on_the_version_of_python(self):
        """The same class must be written the same way everywhere.

        Python 3.11 and Python 3.12 answer differently when asked
        whether a class is a protocol, and the signature of
        ``Enum.__init__`` changed between 3.12 and 3.13.  The generator
        must not follow either, or the same code produces a different
        page depending on the interpreter that runs it.
        """
        sys.path.insert(0, str(ROOT / "tools"))
        import generate_docs

        from netforge.connectivity import TcpConnection
        from netforge.models.risk import RiskLevel
        from netforge.sentinel.engine import Rule

        assert generate_docs.the_signature_of(TcpConnection) == (
            "(host: str, port: int, *, timeout: float | None = 30.0)"
        )
        assert generate_docs.the_signature_of(RiskLevel) == "()"
        assert generate_docs.the_signature_of(Rule) == "()"

    def test_the_generator_changes_nothing(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import generate_docs

        changed = generate_docs.generate(write=False)
        assert changed == [], (
            "the documentation is out of date; run "
            "`python tools/generate_docs.py`:\n" + "\n".join(changed)
        )

    def test_the_generator_writes_the_pages(self, descriptors):
        sys.path.insert(0, str(ROOT / "tools"))
        import generate_docs

        for descriptor in descriptors:
            text = generate_docs.the_operation_page(descriptor)
            page = the_page_of(descriptor.name)
            assert text == page.read_text(encoding="utf-8"), page
