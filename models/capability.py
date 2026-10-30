"""The capability taxonomy.

A capability category answers "what *kind* of thing does this operation
do?".  It maps one-to-one onto the packages of the NetForge framework, so
the category of an operation is also the module it lives in.

The categories are the ones named in the specification: connectivity,
discovery, DNS, protocols, capture, analysis, configuration, security,
manipulation and emulation.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["CapabilityCategory"]


class CapabilityCategory(StrEnum):
    """The kind of capability an operation provides."""

    CONNECTIVITY = "connectivity"
    DISCOVERY = "discovery"
    DNS = "dns"
    PROTOCOLS = "protocols"
    CAPTURE = "capture"
    ANALYSIS = "analysis"
    CONFIGURATION = "configuration"
    SECURITY = "security"
    MANIPULATION = "manipulation"
    EMULATION = "emulation"

    @property
    def label(self) -> str:
        """Return the human-readable name of the category."""
        return self.name.replace("_", " ").title()

    @property
    def description(self) -> str:
        """Return a one-line description of what the category covers."""
        return _DESCRIPTIONS[self]

    @classmethod
    def parse(cls, value: "str | CapabilityCategory") -> "CapabilityCategory":
        """Coerce ``value`` into a :class:`CapabilityCategory`."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError(f"cannot interpret {value!r} as a capability category")
        text = value.strip().lower().replace("-", "_").replace(" ", "_")
        try:
            return cls(text)
        except ValueError as exc:
            raise ValueError(f"unknown capability category: {value!r}") from exc


_DESCRIPTIONS: dict[CapabilityCategory, str] = {
    CapabilityCategory.CONNECTIVITY: "Communication mechanisms used to reach remote systems.",
    CapabilityCategory.DISCOVERY: "Identifying hosts, services and network topology.",
    CapabilityCategory.DNS: "DNS diagnostics and record analysis.",
    CapabilityCategory.PROTOCOLS: "Protocol-specific implementations and abstractions.",
    CapabilityCategory.CAPTURE: "Traffic acquisition and capture sessions.",
    CapabilityCategory.ANALYSIS: "Network and traffic analysis.",
    CapabilityCategory.CONFIGURATION: "Remote configuration and administration.",
    CapabilityCategory.SECURITY: "Security assessment and defensive testing.",
    CapabilityCategory.MANIPULATION: "Controlled traffic modification.",
    CapabilityCategory.EMULATION: "Network condition simulation.",
}
