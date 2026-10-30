"""The documentation must match the code.

The registry is the only source of truth about what NetForge can do.  The
documentation is derived from it, and these tests are what keeps the
derivation honest: a package that publishes an operation has a page, the
page names the operation, the top-level README links to the entry point
of every package, and every link in the documentation resolves.

The tests are the reason the documentation cannot quietly rot.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from netforge.core.bootstrap import builtin_registry  # noqa: E402

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
    """The operations grouped by the package that publishes them."""
    grouped: dict[str, list] = {}
    for descriptor in descriptors:
        grouped.setdefault(descriptor.category.value, []).append(descriptor)
    return grouped


def the_page_of(operation: str, category: str) -> Path:
    """The path of the page of an operation."""
    prefix = f"{category}."
    name = operation[len(prefix):] if operation.startswith(prefix) else operation
    return DOCS / category / f"{name}.md"


class TestEveryOperationHasAPage:
    """The pages of the operations."""

    def test_every_operation_has_a_page(self, descriptors):
        missing = [
            descriptor.name
            for descriptor in descriptors
            if not the_page_of(descriptor.name, descriptor.category.value).is_file()
        ]
        assert missing == [], f"these operations have no page: {missing}"

    def test_the_page_names_the_operation(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name, descriptor.category.value)
            text = page.read_text(encoding="utf-8")
            assert f"# `{descriptor.name}`" in text, page

    def test_the_page_carries_the_summary(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name, descriptor.category.value)
            text = page.read_text(encoding="utf-8")
            assert descriptor.summary in text, page

    def test_the_page_carries_the_risk(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name, descriptor.category.value)
            text = page.read_text(encoding="utf-8")
            assert descriptor.risk_level.label in text, page

    def test_the_page_documents_every_request_parameter(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name, descriptor.category.value)
            text = page.read_text(encoding="utf-8")
            properties = (descriptor.request_schema or {}).get("properties") or {}
            for name in properties:
                assert f"`{name}`" in text, f"{page}: the parameter {name}"

    def test_the_page_documents_every_response_field(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name, descriptor.category.value)
            text = page.read_text(encoding="utf-8")
            properties = (descriptor.response_schema or {}).get("properties") or {}
            for name in properties:
                assert f"`{name}`" in text, f"{page}: the field {name}"

    def test_the_page_links_to_the_package(self, descriptors):
        for descriptor in descriptors:
            page = the_page_of(descriptor.name, descriptor.category.value)
            text = page.read_text(encoding="utf-8")
            assert "](README.md)" in text, page


class TestEveryPackageHasAnEntryPoint:
    """The folders of the packages."""

    def test_every_package_has_a_folder(self, descriptors):
        for category in the_packages(descriptors):
            assert (DOCS / category).is_dir(), f"{category} has no folder"

    def test_every_package_has_an_entry_point(self, descriptors):
        for category in the_packages(descriptors):
            entry = DOCS / category / "README.md"
            assert entry.is_file(), f"{category} has no entry point"

    def test_the_entry_point_lists_every_operation(self, descriptors):
        for category, operations in the_packages(descriptors).items():
            text = (DOCS / category / "README.md").read_text(encoding="utf-8")
            for descriptor in operations:
                assert descriptor.name in text, f"{category}: {descriptor.name}"

    def test_the_entry_point_lists_the_public_api(self, descriptors):
        for category in the_packages(descriptors):
            text = (DOCS / category / "README.md").read_text(encoding="utf-8")
            assert "<!-- generated:public-api -->" in text, category


class TestTheTopLevelReadme:
    """The entry point of every package has to be reachable from the README."""

    def test_the_readme_links_to_every_entry_point(self, descriptors):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        missing = [
            category
            for category in the_packages(descriptors)
            if f"docs/{category}/README.md" not in text
        ]
        assert missing == [], f"the README does not link to: {missing}"

    def test_the_readme_links_to_the_documentation_index(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        assert "docs/README.md" in text


class TestEveryLinkResolves:
    """A link that does not resolve is a broken door."""

    def the_documents(self):
        yield from sorted(DOCS.rglob("*.md"))

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
            page = the_page_of(descriptor.name, descriptor.category.value)
            assert text == page.read_text(encoding="utf-8"), page
